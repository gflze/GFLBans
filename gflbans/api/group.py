from datetime import datetime
from typing import Tuple, Optional, List

from bson import ObjectId
from dateutil.tz import UTC
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import ORJSONResponse
from starlette.requests import Request

from gflbans.api.auth import check_access, csrf_protect
from gflbans.internal.config import MONGO_DB
from gflbans.internal.constants import NOT_AUTHED_USER, AUTHED_USER
from gflbans.internal.database.audit_log import DAuditLog, EVENT_SET_GROUP_PERMISSIONS
from gflbans.internal.database.group import DGroup
from gflbans.internal.flags import PERMISSION_MANAGE_GROUPS
from gflbans.internal.integrations.ips import get_groups as py_get_groups
from gflbans.internal.log import logger
from gflbans.internal.models.api import Group
from gflbans.internal.models.protocol import SetGroupPerms

group_router = APIRouter(default_response_class=ORJSONResponse)


@group_router.get('/', response_model_exclude_unset=True, response_model_exclude_none=True,
                  response_model=List[Group])
async def get_groups(request: Request, auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)):
    if auth[0] == NOT_AUTHED_USER: raise HTTPException(status_code=401, detail='You must be authenticated to do this!')

    if auth[2] & PERMISSION_MANAGE_GROUPS != PERMISSION_MANAGE_GROUPS:
        raise HTTPException(detail='You do not have permission to do this!', status_code=403)

    groups = await py_get_groups(request.app)

    results = []

    for group in groups:
        dg = await DGroup.find_one_from_query(request.app.state.db[MONGO_DB], {'ips_group': group['id']})

        if dg is None:
            dg = DGroup(privileges=0, ips_group=group['id'])
            await dg.commit(request.app.state.db[MONGO_DB])

        results.append(Group(group_name=group['name'], group_id=group['id'], permissions=dg.privileges))

    return results


@group_router.patch('/{ips_group}', dependencies=[Depends(csrf_protect)], response_model_exclude_unset=True,
                    response_model_exclude_none=True)
async def set_group_permissions(request: Request, ips_group: int, q: SetGroupPerms,
                                auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)):
    if auth[0] == NOT_AUTHED_USER: raise HTTPException(status_code=401, detail='You must be authenticated to do this!')

    if auth[2] & PERMISSION_MANAGE_GROUPS != PERMISSION_MANAGE_GROUPS:
        raise HTTPException(detail='You do not have permission to do this!', status_code=403)

    dg = await DGroup.find_one_from_query(request.app.state.db[MONGO_DB], {'ips_group': ips_group})

    if dg is None:
        dg = DGroup(privileges=0, ips_group=ips_group)

    dg.privileges = q.permissions

    ev_string = f'{auth[0]}/{auth[1]} set the permissions of {ips_group} to {q.permissions}'

    logger.info(ev_string)

    i = auth[1] if auth[1] == AUTHED_USER else None

    await DAuditLog(time=datetime.now(tz=UTC), event_type=EVENT_SET_GROUP_PERMISSIONS, initiator=i,
                    message=ev_string, key_pair=(auth[0], auth[1])).commit(request.app.state.db[MONGO_DB])

    await dg.commit(request.app.state.db[MONGO_DB])
