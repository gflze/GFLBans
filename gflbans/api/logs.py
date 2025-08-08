from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import ORJSONResponse
from pymongo import DESCENDING
from starlette.requests import Request

from gflbans.api.auth import AuthInfo, check_access
from gflbans.internal.config import MONGO_DB
from gflbans.internal.constants import AUTHED_USER, NOT_AUTHED_USER, SERVER_KEY
from gflbans.internal.database.audit_log import DAuditLog
from gflbans.internal.database.dadmin import DAdmin
from gflbans.internal.database.server import DServer
from gflbans.internal.flags import PERMISSION_VIEW_AUDIT_LOGS
from gflbans.internal.models.api import AuditLog, Initiator
from gflbans.internal.models.protocol import GetAuditLogs, GetAuditLogsReply
from gflbans.internal.pyapi_utils import load_admin_from_initiator

log_router = APIRouter(default_response_class=ORJSONResponse)


# Makes it so FastAPI can parse ObjectIDs by converting them recursively to strings
def sanitize_json(value):
    if isinstance(value, ObjectId):
        return str(value)
    elif isinstance(value, dict):
        return {k: sanitize_json(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [sanitize_json(v) for v in value]
    elif isinstance(value, tuple):
        return tuple(sanitize_json(v) for v in value)
    else:
        return value


async def as_auditlog(app, log: DAuditLog) -> AuditLog:
    admin = await DAdmin.from_id(app.state.db[MONGO_DB], log.admin)
    if admin and admin.name:
        admin = admin.name
    elif admin:
        admin = admin.ips_user
    else:
        admin = 'System'

    if log.authentication_type == AUTHED_USER:
        auther = admin
    elif log.authentication_type == SERVER_KEY:
        auther = await DServer.from_id(app.state.db[MONGO_DB], log.authenticator)
        if auther and auther.friendly_name:
            auther = auther.friendly_name
        elif auther:
            auther = f'{auther.ip}:{auther.game_port}'
    else:
        auther = sanitize_json(log.authenticator)

    return AuditLog(
        time=log.time,
        event_type=log.event_type,
        authentication_type=log.authentication_type,
        authenticator=auther,
        admin=admin,
        old_item=sanitize_json(log.old_item),
        new_item=sanitize_json(log.new_item),
    )


@log_router.post(
    '/',
    response_model=GetAuditLogsReply,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def get_audit_logs(request: Request, query: GetAuditLogs, auth: AuthInfo = Depends(check_access)):
    if auth.type == NOT_AUTHED_USER:
        raise HTTPException(status_code=401, detail='You must be authenticated to do this!')

    if auth.permissions & PERMISSION_VIEW_AUDIT_LOGS != PERMISSION_VIEW_AUDIT_LOGS:
        raise HTTPException(detail='You do not have permission to do this!', status_code=403)

    q = {}

    if query.event_type:
        if len(query.event_type) == 1:
            q['event_type'] = query.event_type[0]
        else:
            q['event_type'] = {'$in': query.event_type}

    if query.authenticator is not None:
        q['authenticator'] = ObjectId(query.authenticator)

    if query.admin is not None:
        if query.admin.startswith('-'):
            q['admin'] = {'$exists': False}
        else:
            admin = await load_admin_from_initiator(request.app, Initiator(ips_id=query.admin))
            if admin:
                q['admin'] = admin.mongo_admin_id

    logs = []

    async for dlog in DAuditLog.from_query(
        request.app.state.db[MONGO_DB], q, limit=query.limit, skip=query.skip, sort=('time', DESCENDING)
    ):
        logs.append(await as_auditlog(request.app, dlog))

    return GetAuditLogsReply(results=logs, total_matched=await DAuditLog.count(request.app.state.db[MONGO_DB], q))
