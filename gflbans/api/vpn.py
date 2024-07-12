import re
from datetime import datetime
from typing import Optional, Tuple

from bson import ObjectId
from dateutil.tz import UTC
from fastapi import Depends, HTTPException, APIRouter
from fastapi.responses import ORJSONResponse
from pydantic import conint
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError
from starlette.requests import Request
from starlette.responses import Response

from gflbans.api.auth import check_access
from gflbans.internal.config import MONGO_DB
from gflbans.internal.constants import NOT_AUTHED_USER
from gflbans.internal.database.dadmin import DAdmin
from gflbans.internal.database.vpn import DVPN
from gflbans.internal.errors import NoSuchAdminError
from gflbans.internal.flags import PERMISSION_MANAGE_VPNS, PERMISSION_VPN_CHECK_SKIP
from gflbans.internal.models.api import PositiveIntIncl0, AdminMinimal, Initiator, VPNInfo
from gflbans.internal.models.protocol import FetchWhitelistReply, AddVPN, RemoveVPN, FetchBlocklistReply
from gflbans.internal.pyapi_utils import load_admin_from_initiator
from gflbans.internal.search import do_whitelist_search

vpn_router = APIRouter(default_response_class=ORJSONResponse)


# Define a dependency since all of these require management perms
async def ensure_management_privs(auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)):
    if auth[0] == NOT_AUTHED_USER: raise HTTPException(status_code=401, detail='You must be authenticated to do this!')

    if auth[2] & PERMISSION_MANAGE_VPNS != PERMISSION_MANAGE_VPNS:
        raise HTTPException(status_code=403, detail='You do not have permission to do this!')


@vpn_router.get('/whitelist', response_model=FetchWhitelistReply, response_model_exclude_none=True,
                response_model_exclude_unset=True, dependencies=[Depends(ensure_management_privs)])
async def fetch_whitelist(request: Request, skip: PositiveIntIncl0, limit: conint(gt=0, le=50),
                          sort=('ips_user', ASCENDING)):
    qc = {'vpn_whitelist': True}

    ais = []

    async for dadm in DAdmin.from_query(request.app.state.db[MONGO_DB], qc, limit=limit, skip=skip, sort=sort):
        gridfs_file = None

        if dadm.avatar is not None:
            gridfs_file = dadm.avatar.gridfs_file

        ais.append(AdminMinimal(admin_name=dadm.name, admin_id=dadm.ips_user, avatar_id=gridfs_file))

    return FetchWhitelistReply(results=ais, total_whitelist=await DAdmin.count(request.app.state.db[MONGO_DB], qc))


@vpn_router.get('/whitelist/search', response_model=FetchWhitelistReply, response_model_exclude_none=True,
                response_model_exclude_unset=True, dependencies=[Depends(ensure_management_privs)])
async def fetch_whitelist(request: Request, query: str, limit: conint(gt=0, le=50), skip: PositiveIntIncl0):
    qc = await do_whitelist_search(query)

    ais = []

    async for dadm in DAdmin.from_query(request.app.state.db[MONGO_DB], qc, limit=limit, skip=skip,
                                        sort=('ips_user', ASCENDING)):
        gridfs_file = None

        if dadm.avatar is not None:
            gridfs_file = dadm.avatar.gridfs_file

        ais.append(AdminMinimal(admin_name=dadm.name, admin_id=dadm.ips_user, avatar_id=gridfs_file))

    return FetchWhitelistReply(results=ais, total_whitelist=await DAdmin.count(request.app.state.db[MONGO_DB], qc))


@vpn_router.put('/whitelist', dependencies=[Depends(ensure_management_privs)])
async def add_whitelist(request: Request, admin: Initiator):
    try:
        adm = await load_admin_from_initiator(request.app, admin)
    except NoSuchAdminError:
        raise HTTPException(status_code=404, detail='The admin could not be found')

    if adm.permissions & PERMISSION_VPN_CHECK_SKIP == PERMISSION_VPN_CHECK_SKIP:
        return Response(status_code=204)

    dadm = await DAdmin.from_id(request.app.state.db[MONGO_DB], adm.mongo_admin_id)

    dadm.vpn_whitelist = True

    await dadm.commit(request.app.state.db[MONGO_DB])

    return Response(status_code=204)


@vpn_router.delete('/whitelist', dependencies=[Depends(ensure_management_privs)])
async def add_whitelist(request: Request, admin: Initiator):
    try:
        adm = await load_admin_from_initiator(request.app, admin)
    except NoSuchAdminError:
        raise HTTPException(status_code=404, detail='The admin could not be found')

    if adm.permissions & PERMISSION_VPN_CHECK_SKIP != PERMISSION_VPN_CHECK_SKIP:
        return Response(status_code=204)

    dadm = await DAdmin.from_id(request.app.state.db[MONGO_DB], adm.mongo_admin_id)

    dadm.vpn_whitelist = False

    await dadm.commit(request.app.state.db[MONGO_DB])

    return Response(status_code=204)


@vpn_router.put('/', dependencies=[Depends(ensure_management_privs)])
async def add_vpn(request: Request, vpn: AddVPN):
    b_asn = True if vpn.vpn_type == 'asn' else False
    payload = str(vpn.as_number) if b_asn else vpn.cidr

    dv = DVPN(is_asn=b_asn, is_cloud=vpn.is_cloud, payload=payload, comment=vpn.comment,
              added_on=int(datetime.now(tz=UTC).timestamp()))

    try:
        await dv.commit(request.app.state.db[MONGO_DB])
    except DuplicateKeyError:
        raise HTTPException(detail='VPN is already on the blocklist', status_code=409)

    return Response(status_code=204)


@vpn_router.delete('/', dependencies=[Depends(ensure_management_privs)])
async def remove_vpn(request: Request, vpn: RemoveVPN):
    await request.app.state.db[MONGO_DB][DVPN.__collection__].delete_one({'payload': vpn.as_number_or_cidr})
    return Response(status_code=204)


@vpn_router.get('/', dependencies=[Depends(ensure_management_privs)], response_model=FetchBlocklistReply,
                response_model_exclude_unset=True, response_model_exclude_none=True)
async def fetch_blocklist(request: Request, skip: PositiveIntIncl0 = 0, limit: conint(gt=0, le=50) = 50,
                          block_filter: Optional[str] = None):
    if block_filter is None:
        q = {}
    else:
        q = {
            '$or': [
                {'payload': {'$regex': re.escape(block_filter), '$options': 'i'}},
                {'comment': {'$regex': re.escape(block_filter), '$options': 'i'}}
            ]
        }

    dvs = []

    async for dv in DVPN.from_query(request.app.state.db[MONGO_DB], q, skip=skip, sort=('added_on', ASCENDING),
                                    limit=limit):
        vt = 'asn' if dv.is_asn else 'cidr'
        a = VPNInfo(vpn_type=vt, is_cloud=dv.is_cloud, comment=dv.comment)

        if vt == 'asn':
            a.as_number = int(dv.payload)
        else:
            a.cidr = dv.payload

        dvs.append(a)

    return FetchBlocklistReply(results=dvs, total_blocks=await DVPN.count(request.app.state.db[MONGO_DB], q))
