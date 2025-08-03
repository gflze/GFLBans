from datetime import datetime
from typing import List

from dateutil.tz import UTC
from fastapi import APIRouter, Depends, HTTPException
from pymongo import DESCENDING
from starlette.requests import Request

from gflbans.api.auth import AuthInfo, check_access, csrf_protect
from gflbans.api_util import as_admin
from gflbans.internal.config import MONGO_DB
from gflbans.internal.constants import NOT_AUTHED_USER
from gflbans.internal.database.audit_log import EVENT_SET_ADMIN_PERMISSIONS, DAuditLog
from gflbans.internal.database.common import DFile
from gflbans.internal.database.dadmin import DAdmin
from gflbans.internal.flags import PERMISSION_MANAGE_GROUPS_AND_ADMINS
from gflbans.internal.integrations.games.steam import _get_steam_user_info
from gflbans.internal.integrations.ips import (
    ips_get_gsid_from_member_id,
    ips_get_member_id_from_gsid,
    ips_process_avatar,
)
from gflbans.internal.log import logger
from gflbans.internal.models.api import AdminInfo, UpdateAdminInfo
from gflbans.internal.models.protocol import GetAdmins
from gflbans.internal.search import id64_or_none

admin_router = APIRouter()


@admin_router.get(
    '/', response_model=List[AdminInfo], response_model_exclude_unset=True, response_model_exclude_none=True
)
async def get_admins(request: Request, query: GetAdmins = Depends(GetAdmins)):
    mongodb_query = {}
    if query.admin.admin_id is not None and query.admin.admin_name is not None:
        mongodb_query['$or'] = [{'ips_user': query.admin.admin_id}, {'name': query.admin.admin_name}]
    elif query.admin.admin_id is not None:
        mongodb_query['ips_user'] = query.admin.admin_id
    elif query.admin.admin_name is not None:
        mongodb_query['name'] = query.admin.admin_name

    group_query = {'groups': {'$exists': True, '$not': {'$size': 0}}}

    if query.admin.group_id is not None:
        group_query['groups']['$all'] = [query.admin.group_id]

    if len(mongodb_query) == 0:
        mongodb_query = group_query
    else:
        mongodb_query = {'$and': [mongodb_query, group_query]}

    admin_list = []
    async for admin in DAdmin.from_query(
        request.app.state.db[MONGO_DB], mongodb_query, limit=query.limit, skip=query.skip, sort=('name', DESCENDING)
    ):
        admin_info = await as_admin(request.app, admin)
        if admin_info is not None and (
            query.admin.permissions is None
            or admin_info.permissions & query.admin.permissions == query.admin.permissions
        ):
            admin_list.append(admin_info)

    return admin_list


@admin_router.put(
    '/', response_model_exclude_unset=True, response_model_exclude_none=True, dependencies=[Depends(csrf_protect)]
)
async def update_admin(request: Request, uai_query: UpdateAdminInfo, auth: AuthInfo = Depends(check_access)):
    if auth.type == NOT_AUTHED_USER:
        raise HTTPException(status_code=401, detail='You must be authenticated to do this!')

    if auth.permissions & PERMISSION_MANAGE_GROUPS_AND_ADMINS != PERMISSION_MANAGE_GROUPS_AND_ADMINS:
        raise HTTPException(detail='You do not have permission to do this!', status_code=403)

    ips_user = ips_get_member_id_from_gsid(await id64_or_none(request.app, uai_query.admin_id))

    target_info = await DAdmin.from_ips_user(request.app.state.db[MONGO_DB], ips_user)

    if target_info is None:
        target_info = DAdmin(ips_user=ips_user)

    original_admin_info = target_info  # For Audit logging purposes
    target_info.last_updated = datetime.now(tz=UTC).timestamp()
    target_info.groups = uai_query.groups

    if uai_query.admin_name is not None:
        target_info.name = uai_query.admin_name

    try:
        steam_json = await _get_steam_user_info(request.app, ips_get_gsid_from_member_id(ips_user))
        if target_info.name is None:
            target_info.name = steam_json['personaname']
        av = DFile(**await ips_process_avatar(request.app, steam_json['avatarfull']))
    except Exception:
        av = None

    if av is not None:
        target_info.avatar = av

    logger.info(f'{auth.type}/{auth.authenticator_id} set the groups of {ips_user} to {uai_query.groups}')

    await DAuditLog(
        time=datetime.now(tz=UTC).timestamp(),
        event_type=EVENT_SET_ADMIN_PERMISSIONS,
        authentication_type=auth.type,
        authenticator=auth.authenticator_id,
        admin=auth.admin.mongo_admin_id if auth.admin else None,
        old_item=original_admin_info.dict(),
        new_item=target_info.dict(),
    ).commit(request.app.state.db[MONGO_DB])

    await target_info.commit(request.app.state.db[MONGO_DB])
