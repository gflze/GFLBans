from datetime import datetime
from typing import List

from dateutil.tz import UTC
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import ORJSONResponse
from starlette.requests import Request

from gflbans.api.auth import AuthInfo, check_access, csrf_protect
from gflbans.internal.config import MONGO_DB
from gflbans.internal.constants import NOT_AUTHED_USER
from gflbans.internal.database.audit_log import (
    EVENT_ADD_GROUP,
    EVENT_DELETE_GROUP,
    EVENT_SET_GROUP_PERMISSIONS,
    DAuditLog,
)
from gflbans.internal.database.dadmin import DAdmin
from gflbans.internal.database.group import DGroup
from gflbans.internal.flags import PERMISSION_MANAGE_GROUPS_AND_ADMINS
from gflbans.internal.integrations.ips import get_groups as py_get_groups
from gflbans.internal.log import logger
from gflbans.internal.models.api import Group, PositiveIntIncl0
from gflbans.internal.models.protocol import UpdateGroup

group_router = APIRouter(default_response_class=ORJSONResponse)


@group_router.get('/', response_model_exclude_unset=True, response_model_exclude_none=True, response_model=List[Group])
async def get_groups(request: Request):
    groups = await py_get_groups(request.app)

    results = []

    for group in groups:
        results.append(Group(group_name=group['name'], group_id=group['ips_group'], permissions=group['privileges']))

    return results


@group_router.get(
    '/{ips_group}', response_model_exclude_unset=True, response_model_exclude_none=True, response_model=Group
)
async def get_group(request: Request, ips_group: PositiveIntIncl0):
    group = await request.app.state.db[MONGO_DB]['groups'].find_one({'ips_group': ips_group})

    if group is None:
        raise HTTPException(detail='No group exists with ips_group: {ips_group}', status_code=404)

    return Group(group_name=group['name'], group_id=group['ips_group'], permissions=group['privileges'])


@group_router.post(
    '/', dependencies=[Depends(csrf_protect)], response_model_exclude_unset=True, response_model_exclude_none=True
)
async def update_group(request: Request, ug_query: UpdateGroup, auth: AuthInfo = Depends(check_access)):
    if auth.type == NOT_AUTHED_USER:
        raise HTTPException(status_code=401, detail='You must be authenticated to do this!')

    if auth.permissions & PERMISSION_MANAGE_GROUPS_AND_ADMINS != PERMISSION_MANAGE_GROUPS_AND_ADMINS:
        raise HTTPException(detail='You do not have permission to do this!', status_code=403)
    # Try to find lowest unused value to set new ips_group to
    groups = await py_get_groups(request.app)
    available_groups = list(range(len(groups) + 1))
    for grp in groups:
        if grp['ips_group'] in available_groups:
            available_groups.remove(grp['ips_group'])

    new_group = DGroup(ips_group=available_groups[0], name=ug_query.name, privileges=ug_query.privileges)

    logger.info(
        f'{auth.type}/{auth.authenticator_id} created group '
        f'{new_group.ips_group} with privileges {new_group.privileges}'
    )

    await DAuditLog(
        time=datetime.now(tz=UTC).timestamp(),
        event_type=EVENT_ADD_GROUP,
        authentication_type=auth.type,
        authenticator=auth.authenticator_id,
        admin=auth.admin.mongo_admin_id,
        new_item=new_group.dict(),
    ).commit(request.app.state.db[MONGO_DB])

    await new_group.commit(request.app.state.db[MONGO_DB])
    await py_get_groups(request.app, True)  # Update redis cache


@group_router.delete(
    '/{ips_group}',
    dependencies=[Depends(csrf_protect)],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def delete_group(request: Request, ips_group: int, auth: AuthInfo = Depends(check_access)):
    if auth.type == NOT_AUTHED_USER:
        raise HTTPException(status_code=401, detail='You must be authenticated to do this!')

    if auth.permissions & PERMISSION_MANAGE_GROUPS_AND_ADMINS != PERMISSION_MANAGE_GROUPS_AND_ADMINS:
        raise HTTPException(detail='You do not have permission to do this!', status_code=403)
    dg = await DGroup.find_one_from_query(request.app.state.db[MONGO_DB], {'ips_group': ips_group})

    if dg is None:
        raise HTTPException(detail='No group exists with ips_group: {ips_group}', status_code=404)

    mongodb_query = {'groups': {'$exists': True, '$all': [ips_group]}}

    async for admin in DAdmin.from_query(request.app.state.db[MONGO_DB], mongodb_query):
        # Delete the group from all admins with it
        # This way if a new group is added later with the same id, they dont automatically get the new one
        admin.groups.remove(ips_group)
        await admin.commit(request.app.state.db[MONGO_DB])

    logger.info(f'{auth.type}/{auth.authenticator_id} deleted group {ips_group}')

    await DAuditLog(
        time=datetime.now(tz=UTC).timestamp(),
        event_type=EVENT_DELETE_GROUP,
        authentication_type=auth.type,
        authenticator=auth.authenticator_id,
        admin=auth.admin.mongo_admin_id,
        old_item=dg.dict(),
    ).commit(request.app.state.db[MONGO_DB])

    await request.app.state.db[MONGO_DB][DGroup.__collection__].delete_one({'ips_group': ips_group})
    await py_get_groups(request.app, True)  # Update redis cache


@group_router.patch(
    '/{ips_group}',
    dependencies=[Depends(csrf_protect)],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def patch_group(
    request: Request,
    ips_group: int,
    ug_query: UpdateGroup,
    auth: AuthInfo = Depends(check_access),
):
    if auth.type == NOT_AUTHED_USER:
        raise HTTPException(status_code=401, detail='You must be authenticated to do this!')

    if auth.permissions & PERMISSION_MANAGE_GROUPS_AND_ADMINS != PERMISSION_MANAGE_GROUPS_AND_ADMINS:
        raise HTTPException(detail='You do not have permission to do this!', status_code=403)
    dg = await DGroup.find_one_from_query(request.app.state.db[MONGO_DB], {'ips_group': ips_group})

    if dg is None:
        raise HTTPException(detail='No group exists with ips_group: {ips_group}', status_code=404)

    original_group_info = dg  # For audit logging purposes
    dg.name = ug_query.name
    dg.privileges = ug_query.privileges

    logger.info(
        f'{auth.type}/{auth.authenticator_id} patched the permissions of {dg.ips_group} to {ug_query.privileges}'
    )

    await DAuditLog(
        time=datetime.now(tz=UTC).timestamp(),
        event_type=EVENT_SET_GROUP_PERMISSIONS,
        authentication_type=auth.type,
        authenticator=auth.authenticator_id,
        admin=auth.admin.mongo_admin_id,
        old_item=original_group_info.dict(),
        new_item=dg.dict(),
    ).commit(request.app.state.db[MONGO_DB])

    await dg.commit(request.app.state.db[MONGO_DB])
    await py_get_groups(request.app, True)  # Update redis cache
