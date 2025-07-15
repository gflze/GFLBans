import re
from datetime import datetime
from typing import Optional, Tuple

from bson import ObjectId
from dateutil.tz import UTC
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import ORJSONResponse
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError
from starlette.requests import Request
from starlette.responses import Response

from gflbans.api.auth import check_access, csrf_protect
from gflbans.internal.config import MONGO_DB
from gflbans.internal.constants import AUTHED_USER, NOT_AUTHED_USER
from gflbans.internal.database.audit_log import EVENT_DELETE_VPN, EVENT_EDIT_VPN, EVENT_NEW_VPN, DAuditLog
from gflbans.internal.database.vpn import DVPN
from gflbans.internal.flags import PERMISSION_MANAGE_VPNS
from gflbans.internal.log import logger
from gflbans.internal.models.api import VPNInfo
from gflbans.internal.models.protocol import AddVPN, FetchBlocklistReply, PatchVPN, RemoveVPN

vpn_router = APIRouter(default_response_class=ORJSONResponse)


# Define a dependency since all of these require management perms
async def ensure_management_privs(auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)):
    if auth[0] == NOT_AUTHED_USER:
        raise HTTPException(status_code=401, detail='You must be authenticated to do this!')

    if auth[2] & PERMISSION_MANAGE_VPNS != PERMISSION_MANAGE_VPNS:
        raise HTTPException(status_code=403, detail='You do not have permission to do this!')

    return auth


@vpn_router.post(
    '/',
    response_model_exclude_none=True,
    response_model_exclude_unset=True,
    response_model=VPNInfo,
    dependencies=[
        Depends(ensure_management_privs),
        Depends(csrf_protect),
    ],
)
async def add_vpn(request: Request, vpn: AddVPN, auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)):
    b_asn = True if vpn.vpn_type == 'asn' else False
    payload = str(vpn.as_number) if b_asn else vpn.cidr

    dv = DVPN(
        is_asn=b_asn,
        is_dubious=vpn.is_dubious,
        payload=payload,
        comment=vpn.comment,
        added_on=int(datetime.now(tz=UTC).timestamp()),
    )

    try:
        await dv.commit(request.app.state.db[MONGO_DB])
    except DuplicateKeyError:
        raise HTTPException(detail='VPN is already on the blocklist', status_code=409)

    ev_string = f'{auth[0]}/{auth[1]} created a VPN {dv.id}'

    logger.info(ev_string)

    i = auth[1] if auth[1] == AUTHED_USER else None

    await DAuditLog(
        time=datetime.now(tz=UTC),
        event_type=EVENT_NEW_VPN,
        initiator=i,
        message=ev_string,
        key_pair=(auth[0], auth[1]),
    ).commit(request.app.state.db[MONGO_DB])

    return VPNInfo(
        id=str(dv.id),
        vpn_type='asn' if dv.is_asn else 'cidr',
        is_dubious=dv.is_dubious,
        as_number=dv.payload if dv.is_asn else None,
        cidr=dv.payload if not dv.is_asn else None,
        comment=dv.comment,
    )


@vpn_router.patch(
    '/',
    response_model_exclude_none=True,
    response_model_exclude_unset=True,
    response_model=VPNInfo,
    dependencies=[
        Depends(ensure_management_privs),
        Depends(csrf_protect),
    ],
)
async def patch_vpn(
    request: Request, vpn_patch: PatchVPN, auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)
):
    vpn = await DVPN.from_id(request.app.state.db[MONGO_DB], vpn_patch.id)

    if vpn is None:
        raise HTTPException(detail='VPN does not exist', status_code=404)

    modifications = 'SET'

    if vpn_patch.vpn_type is not None:
        is_asn = True if vpn_patch.vpn_type == 'asn' else False
        if is_asn != vpn.is_asn:
            vpn.is_asn = is_asn
            modifications += f', is_asn = {vpn.is_asn}'

    if vpn_patch.as_number is not None or vpn_patch.cidr is not None:
        payload = str(vpn_patch.as_number) if vpn.is_asn else vpn_patch.cidr
        if payload != vpn.payload:
            vpn.payload = payload
            modifications += f', payload = {vpn.payload}'

    if vpn_patch.is_dubious is not None and vpn_patch.is_dubious != vpn.is_dubious:
        vpn.is_dubious = vpn_patch.is_dubious
        modifications += f', is_dubious = {vpn.is_dubious}'

    if vpn_patch.comment is not None and vpn_patch.comment != vpn.comment:
        vpn.comment = vpn_patch.comment
        modifications += f', comment = {vpn.comment}'

    if modifications == 'SET':
        raise HTTPException(status_code=400, detail='Request changes nothing')

    await vpn.commit(request.app.state.db[MONGO_DB])

    ev_string = f'{auth[0]}/{auth[1]} edited a VPN {vpn.id}'

    logger.info(ev_string)

    i = auth[1] if auth[1] == AUTHED_USER else None

    await DAuditLog(
        time=datetime.now(tz=UTC),
        event_type=EVENT_EDIT_VPN,
        initiator=i,
        message=ev_string,
        key_pair=(auth[0], auth[1]),
        long_message=modifications,
    ).commit(request.app.state.db[MONGO_DB])

    return VPNInfo(
        id=str(vpn.id),
        vpn_type='asn' if vpn.is_asn else 'cidr',
        is_dubious=vpn.is_dubious,
        as_number=vpn.payload if vpn.is_asn else None,
        cidr=vpn.payload if not vpn.is_asn else None,
        comment=vpn.comment,
    )


@vpn_router.delete(
    '/',
    response_model_exclude_none=True,
    response_model_exclude_unset=True,
    dependencies=[
        Depends(ensure_management_privs),
        Depends(csrf_protect),
    ],
)
async def remove_vpn(
    request: Request, vpn: RemoveVPN, auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)
):
    delete_type = await request.app.state.db[MONGO_DB][DVPN.__collection__].delete_one(
        {'payload': vpn.as_number_or_cidr}
    )

    if delete_type.deleted_count is None or delete_type.deleted_count == 0:
        raise HTTPException(detail='No VPN exists with identifier: {vpn.as_number_or_cidr}', status_code=404)

    ev_string = f'{auth[0]}/{auth[1]} deleted VPN {vpn.as_number_or_cidr}'

    logger.info(ev_string)

    i = auth[1] if auth[1] == AUTHED_USER else None

    await DAuditLog(
        time=datetime.now(tz=UTC),
        event_type=EVENT_DELETE_VPN,
        initiator=i,
        message=ev_string,
        key_pair=(auth[0], auth[1]),
    ).commit(request.app.state.db[MONGO_DB])
    return Response(status_code=204)


@vpn_router.get(
    '/',
    dependencies=[Depends(ensure_management_privs)],
    response_model=FetchBlocklistReply,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def fetch_blocklist(request: Request, block_filter: Optional[str] = None):
    if block_filter is None:
        q = {}
    else:
        q = {
            '$or': [
                {'payload': {'$regex': re.escape(block_filter), '$options': 'i'}},
                {'comment': {'$regex': re.escape(block_filter), '$options': 'i'}},
            ]
        }

    dvs = []

    async for dv in DVPN.from_query(request.app.state.db[MONGO_DB], q, sort=('added_on', ASCENDING)):
        vt = 'asn' if dv.is_asn else 'cidr'
        a = VPNInfo(id=str(dv.id), vpn_type=vt, is_dubious=dv.is_dubious, comment=dv.comment)

        if vt == 'asn':
            a.as_number = int(dv.payload)
        else:
            a.cidr = dv.payload

        dvs.append(a)

    return FetchBlocklistReply(results=dvs, total_blocks=await DVPN.count(request.app.state.db[MONGO_DB], q))
