import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Set, Tuple, Union

import bson
from bson import ObjectId
from dateutil.tz import UTC
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.openapi.models import Response
from fastapi.responses import ORJSONResponse
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from pymongo import DESCENDING
from starlette.background import BackgroundTasks
from starlette.requests import Request

from gflbans.api.auth import check_access, csrf_protect
from gflbans.api_util import as_infraction, construct_ci_resp, obj_id, should_include_ip, str_id, user_str
from gflbans.internal.asn import VPN_CLOUD, VPN_YES, check_vpn
from gflbans.internal.config import MONGO_DB
from gflbans.internal.constants import AUTHED_USER, NOT_AUTHED_USER, SERVER_KEY
from gflbans.internal.database.audit_log import (
    EVENT_DELETE_COMMENT,
    EVENT_EDIT_COMMENT,
    EVENT_EDIT_INFRACTION,
    EVENT_NEW_COMMENT,
    EVENT_NEW_INFRACTION,
    EVENT_REMOVE_INFRACTION,
    EVENT_UPLOAD_FILE,
    DAuditLog,
)
from gflbans.internal.database.common import DFile
from gflbans.internal.database.infraction import DComment, DInfraction, build_query_dict
from gflbans.internal.database.tiering_policy import DTieringPolicy, DTieringPolicyTier
from gflbans.internal.errors import SearchError
from gflbans.internal.flags import (
    INFRACTION_ADMIN_CHAT_BLOCK,
    INFRACTION_BAN,
    INFRACTION_CALL_ADMIN_BAN,
    INFRACTION_CHAT_BLOCK,
    INFRACTION_ITEM_BLOCK,
    INFRACTION_VOICE_BLOCK,
    PERMISSION_ADMIN_CHAT_BLOCK,
    PERMISSION_ASSIGN_TO_SERVER,
    PERMISSION_ATTACH_FILE,
    PERMISSION_BAN,
    PERMISSION_BLOCK_CHAT,
    PERMISSION_BLOCK_ITEMS,
    PERMISSION_BLOCK_VOICE,
    PERMISSION_CALL_ADMIN_BLOCK,
    PERMISSION_COMMENT,
    PERMISSION_CREATE_INFRACTION,
    PERMISSION_EDIT_ALL_INFRACTIONS,
    PERMISSION_MANAGE_POLICY,
    PERMISSION_SCOPE_GLOBAL,
    PERMISSION_WEB_MODERATOR,
    str2pflag,
)
from gflbans.internal.infraction_utils import (
    check_immunity,
    create_dinfraction,
    create_dinfraction_with_policy,
    discord_notify_create_infraction,
    filter_badchars,
    get_permissions,
    get_user_data,
    get_vpn_data,
    modify_infraction,
    push_state_to_nodes,
)
from gflbans.internal.integrations.games import normalize_id
from gflbans.internal.log import logger
from gflbans.internal.models.api import FileInfo, Infraction, Initiator, TieringPolicy
from gflbans.internal.models.protocol import (
    AddComment,
    CheckInfractions,
    CheckInfractionsReply,
    CreateInfraction,
    CreateInfractionUsingPolicy,
    DeleteComment,
    DeleteFile,
    EditComment,
    GetInfractions,
    GetInfractionsReply,
    InfractionStatisticsReply,
    ModifyInfraction,
    RecursiveSearch,
    RegisterInfractionTieringPolicy,
    RegisterInfractionTieringPolicyReply,
    RemoveInfractionsOfPlayer,
    RemoveInfractionsOfPlayerReply,
    Search,
    UnlinkInfractionTieringPolicy,
)
from gflbans.internal.pyapi_utils import get_acting, load_admin
from gflbans.internal.search import do_infraction_search
from gflbans.internal.utils import slugify

infraction_router = APIRouter(default_response_class=ORJSONResponse)


@infraction_router.get(
    '/', response_model=GetInfractionsReply, response_model_exclude_unset=True, response_model_exclude_none=True
)
async def get_infractions(
    request: Request,
    query: GetInfractions = Depends(GetInfractions),
    load_fast: bool = True,
    auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access),
):
    incl_ip = should_include_ip(auth[0], auth[2])  # Check if we have perms to see IP addresses

    ip = query.ip if incl_ip else None  # If we do not have permissions, force this value to None

    q = build_query_dict(
        auth[0],
        str_id(auth[1]),
        gs_service=query.player.gs_service,
        gs_id=query.player.gs_id,
        ip=ip,
        ignore_others=(not query.include_other_servers),
        active_only=query.active_only,
    )

    infs = []

    async for dinf in DInfraction.from_query(
        request.app.state.db[MONGO_DB], q, limit=query.limit, skip=query.skip, sort=('created', DESCENDING)
    ):
        if load_fast:
            dinf.comments = []
            dinf.files = []
        infs.append(await as_infraction(request.app, dinf, incl_ip))

    return GetInfractionsReply(results=infs, total_matched=await DInfraction.count(request.app.state.db[MONGO_DB], q))


@infraction_router.get(
    '/{infraction_id}/info',
    response_model=Infraction,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def get_infraction(
    request: Request, infraction_id: str, auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)
):
    try:
        inf = await DInfraction.from_id(request.app.state.db[MONGO_DB], infraction_id)
    except bson.errors.InvalidId:
        raise HTTPException(detail='Invalid id', status_code=400)

    if inf is None:
        raise HTTPException(detail='No such infraction', status_code=404)

    return await as_infraction(request.app, inf, should_include_ip(auth[0], auth[2]))


MAX_UNIX_TIMESTAMP = int((datetime.now() + timedelta(days=365 * 100)).timestamp())


@infraction_router.get(
    '/search', response_model=GetInfractionsReply, response_model_exclude_unset=True, response_model_exclude_none=True
)
async def search_infractions(
    request: Request,
    query: Search = Depends(Search),
    load_fast: bool = True,
    auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access),
):
    incl_ip = should_include_ip(auth[0], auth[2])

    try:
        cq = await do_infraction_search(request.app, query, include_ip=incl_ip)
    except SearchError as e:
        raise HTTPException(detail=f'SearchError: {e.args[0]}', status_code=400)

    infs = []

    async for dinf in DInfraction.from_query(
        request.app.state.db[MONGO_DB], cq, limit=query.limit, skip=query.skip, sort=('created', DESCENDING)
    ):
        if load_fast:
            dinf.comments = []
            dinf.files = []

        # If time left is > 100 years, just say it is perma
        if dinf.expires is not None and dinf.expires > MAX_UNIX_TIMESTAMP:
            dinf.expires = None

        infs.append(await as_infraction(request.app, dinf, incl_ip))

    return GetInfractionsReply(results=infs, total_matched=await DInfraction.count(request.app.state.db[MONGO_DB], cq))


async def recursive_infraction_search(
    app,
    ip: Optional[str],
    steam_id: Optional[str],
    depth: int,
    visited_ids: Set[str],
    found_infractions: Set[str],
    limit: int,
    skip: int,
    load_fast: bool,
) -> List[DInfraction]:
    if depth <= 0:
        return []

    query = RecursiveSearch(ip=ip, gs_id=steam_id, limit=limit, skip=skip)
    search_query = await do_infraction_search(app, query, include_ip=True)

    infractions = []
    new_ips = set()
    new_steam_ids = set()

    async for dinf in DInfraction.from_query(app.state.db[MONGO_DB], search_query, sort=('created', DESCENDING)):
        if str(dinf.id) in found_infractions:
            continue  # Skip already found infractions

        if load_fast:
            dinf.comments = []
            dinf.files = []

        found_infractions.add(str(dinf.id))

        # If time left is > 100 years, just say it is perma
        if dinf.expires is not None and dinf.expires > MAX_UNIX_TIMESTAMP:
            dinf.expires = None

        infractions.append(dinf)

        if 'user' in dinf and 'gs_id' in dinf.user and dinf.user.gs_id not in visited_ids:
            new_steam_ids.add(dinf.user.gs_id)
        if 'ip' in dinf and dinf.ip not in visited_ids:
            new_ips.add(dinf.ip)

        visited_ids.update(new_ips)
        visited_ids.update(new_steam_ids)

    for new_ip in new_ips:
        infractions.extend(
            await recursive_infraction_search(
                app, new_ip, None, depth - 1, visited_ids, found_infractions, limit, skip, load_fast
            )
        )
    for new_steam_id in new_steam_ids:
        infractions.extend(
            await recursive_infraction_search(
                app, None, new_steam_id, depth - 1, visited_ids, found_infractions, limit, skip, load_fast
            )
        )

    return infractions


@infraction_router.get(
    '/alt_search',
    response_model=GetInfractionsReply,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def search_recursive_infractions(
    request: Request,
    query: RecursiveSearch = Depends(RecursiveSearch),
    load_fast: bool = True,
    auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access),
):
    incl_ip = should_include_ip(auth[0], auth[2])
    # If we do not have permission to view IP, force it to None
    ip = query.ip if incl_ip else None

    if not ip and not query.gs_id:
        raise HTTPException(status_code=400, detail="At least one of 'ip' or 'gs_id' must be provided.")

    visited_ids = set()
    found_infractions = set()

    infractions = await recursive_infraction_search(
        request.app, ip, query.gs_id, query.depth, visited_ids, found_infractions, query.limit, query.skip, load_fast
    )
    return GetInfractionsReply(
        results=[await as_infraction(request.app, inf, incl_ip) for inf in infractions], total_matched=len(infractions)
    )


@infraction_router.get(
    '/check', response_model=CheckInfractionsReply, response_model_exclude_unset=True, response_model_exclude_none=True
)
async def check_infractions(
    request: Request,
    query: CheckInfractions = Depends(CheckInfractions),
    auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access),
):
    incl_ip = should_include_ip(auth[0], auth[2])  # Check if we have perms to see IP addresses

    ip = query.ip if incl_ip else None  # If we do not have permissions, force this value to None

    if ip is None and query.player is None:
        raise HTTPException(detail='Cannot have both an empty ip and an empty player', status_code=401)

    # run a vpn check
    # do not check by IP if it is a VPN
    if ip:
        vpn_result = await check_vpn(request.app, ip)

        if vpn_result == VPN_YES or vpn_result == VPN_CLOUD:
            ip = None

    q = build_query_dict(
        auth[0],
        str_id(auth[1]),
        gs_service=query.player.gs_service,
        gs_id=query.player.gs_id,
        ip=ip,
        ignore_others=(not query.include_other_servers),
        active_only=True,
    )

    ci_resp = await construct_ci_resp(request.app.state.db[MONGO_DB], q)

    return ci_resp


@infraction_router.get(
    '/stats',
    response_model=InfractionStatisticsReply,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def infraction_stats(
    request: Request,
    query: CheckInfractions = Depends(CheckInfractions),
    auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access),
):
    ip = query.ip if should_include_ip(auth[0], auth[2]) else None

    if ip is None and query.player is None:
        raise HTTPException(detail='Cannot have both an empty ip and an empty player', status_code=401)

    q = build_query_dict(
        auth[0],
        str_id(auth[1]),
        gs_service=query.player.gs_service,
        gs_id=query.player.gs_id,
        ip=ip,
        ignore_others=(not query.include_other_servers),
        active_only=True,
    )

    qv = {'$and': [q, {'flags': {'$bitsAllSet': INFRACTION_VOICE_BLOCK}}]}
    qt = {'$and': [q, {'flags': {'$bitsAllSet': INFRACTION_CHAT_BLOCK}}]}
    qb = {'$and': [q, {'flags': {'$bitsAllSet': INFRACTION_BAN}}]}
    qa = {'$and': [q, {'flags': {'$bitsAllSet': INFRACTION_ADMIN_CHAT_BLOCK}}]}
    qc = {'$and': [q, {'flags': {'$bitsAllSet': INFRACTION_CALL_ADMIN_BAN}}]}
    qi = {'$and': [q, {'flags': {'$bitsAllSet': INFRACTION_ITEM_BLOCK}}]}
    qw = {
        '$and': [
            q,
            {
                'flags': {
                    '#bitsAllClear': INFRACTION_CALL_ADMIN_BAN
                    | INFRACTION_ADMIN_CHAT_BLOCK
                    | INFRACTION_BAN
                    | INFRACTION_CHAT_BLOCK
                    | INFRACTION_VOICE_BLOCK
                    | INFRACTION_ITEM_BLOCK
                }
            },
        ]
    }

    r = await asyncio.gather(
        request.app.state.db[MONGO_DB].infractions.count_documents(qv),
        request.app.state.db[MONGO_DB].infractions.count_documents(qt),
        request.app.state.db[MONGO_DB].infractions.count_documents(qb),
        request.app.state.db[MONGO_DB].infractions.count_documents(qa),
        request.app.state.db[MONGO_DB].infractions.count_documents(qc),
        request.app.state.db[MONGO_DB].infractions.count_documents(qw),
        request.app.state.db[MONGO_DB].infractions.count_documents(qi),
    )

    return InfractionStatisticsReply(
        voice_block_count=r[0],
        text_block_count=r[1],
        ban_count=r[2],
        admin_chat_block_count=r[3],
        call_admin_block_count=r[4],
        warnings_count=r[5],
        item_block_count=r[6],
    )


@infraction_router.post(
    '/register_policy',
    response_model=RegisterInfractionTieringPolicyReply,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    dependencies=[Depends(csrf_protect)],
)
async def register_tiering_policy(
    request: Request,
    query: RegisterInfractionTieringPolicy,
    auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access),
):
    if auth[2] & PERMISSION_MANAGE_POLICY != PERMISSION_MANAGE_POLICY:
        raise HTTPException(detail='Missing required permission PERMISSION_MANAGE_POLICY', status_code=403)

    server = None if query.server is None else ObjectId(query.server)

    if auth[0] == SERVER_KEY:
        server = auth[1]

    dt = DTieringPolicy(
        tiers=[],
        include_other_servers=query.include_other_servers,
        tier_ttl=query.tier_ttl,
        reason=query.default_reason,
        name=query.name,
        server=server,
    )

    for di in query.tiers:
        dt.tiers.append(DTieringPolicyTier(**di.dict()))

    await dt.commit(request.app.state.db[MONGO_DB])

    assert dt.id is not None, '_id was none after insert'

    return RegisterInfractionTieringPolicyReply(policy_id=str(dt.id))


@infraction_router.post(
    '/unlink_policy',
    dependencies=[Depends(csrf_protect)],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def unlink_tiering_policy(
    request: Request,
    query: UnlinkInfractionTieringPolicy,
    auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access),
):
    if auth[2] & PERMISSION_MANAGE_POLICY != PERMISSION_MANAGE_POLICY:
        raise HTTPException(detail='Missing required permission PERMISSION_MANAGE_POLICY', status_code=403)

    dp = await DTieringPolicy.from_id(request.app.state.db[MONGO_DB], ObjectId(query.policy_id))

    if dp is None:
        raise HTTPException(detail='No such policy', status_code=404)

    dp.server = None

    await dp.commit(request.app.state.db[MONGO_DB])

    return Response(status_code=204)


@infraction_router.get(
    '/policies', response_model=List[TieringPolicy], response_model_exclude_unset=True, response_model_exclude_none=True
)
async def get_tiering_policies(
    request: Request, server: str, auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)
):
    if auth[0] == NOT_AUTHED_USER:
        raise HTTPException(detail='This route is only available to authed users', status_code=401)

    pols = []

    async for dpol in DTieringPolicy.from_query(request.app.state.db[MONGO_DB], {'server': ObjectId(server)}):
        pols.append(TieringPolicy(name=dpol.name, server=server, pol_id=str(dpol.id)))

    return pols


@infraction_router.post(
    '/',
    response_model=Infraction,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    dependencies=[Depends(csrf_protect)],
)
async def create_infraction(
    request: Request,
    query: CreateInfraction,
    tasks: BackgroundTasks,
    auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access),
):
    if auth[0] == NOT_AUTHED_USER:
        raise HTTPException(detail='This route requires authorization.', status_code=401)

    acting_admin, acting_admin_id = await get_acting(request, query.admin, auth[0], auth[1])

    # Server
    if query.server is not None:
        if auth[2] & PERMISSION_ASSIGN_TO_SERVER != PERMISSION_ASSIGN_TO_SERVER:
            raise HTTPException(detail='Insufficient permissions to override the server', status_code=403)

        # If infraction is issued through a server and the admin cant issue global punishments,
        # just make the infraction server only
        if (
            auth[0] == SERVER_KEY
            and query.scope == 'global'
            and query.admin is not None
            and acting_admin.permissions & PERMISSION_SCOPE_GLOBAL != PERMISSION_SCOPE_GLOBAL
        ):
            query.scope = 'server'

        server = ObjectId(query.server)
    elif auth[0] == SERVER_KEY and auth[1] is not None:
        server = auth[1]
    else:
        server = None

    if query.player.gs_id and query.allow_normalize:
        query.player.gs_id = await normalize_id(request.app, query.player.gs_service, query.player.gs_id)

    # create a DInfraction
    dinf = create_dinfraction(
        player=query.player,
        reason=query.reason,
        scope=query.scope,
        punishments=query.punishments,
        session=query.session,
        created=query.created,
        duration=query.duration,
        admin=acting_admin_id,
        dec_online=query.dec_online_only,
        server=server,
    )

    rp = get_permissions(dinf)

    if (acting_admin.permissions & rp != rp and not query.import_mode) or auth[2] & rp != rp:
        raise HTTPException(detail='Insufficient privileges', status_code=403)

    aa = acting_admin if acting_admin.mongo_admin_id is not None else None

    if await check_immunity(request.app, dinf, aa):
        raise HTTPException(detail='Your target is immune', status_code=403)

    # Write the dinfraction
    await dinf.commit(request.app.state.db[MONGO_DB])

    # Create audit log entry
    daudit = DAuditLog(
        time=datetime.now(tz=UTC),
        event_type=EVENT_NEW_INFRACTION,
        initiator=acting_admin.mongo_admin_id,
        key_pair=(auth[0], auth[1]),
        message=f'{acting_admin.name} ({acting_admin.ips_id}) created an infraction {dinf.id} with flags'
        f' {dinf.flags} on {user_str(dinf)}, import_mode = {query.import_mode}',
    )

    await daudit.commit(request.app.state.db[MONGO_DB])

    logger.info(
        f'{acting_admin.name} ({acting_admin.ips_id}) created an infraction {dinf.id} with flags {dinf.flags}'
        f' on {user_str(dinf)}, import_mode = {query.import_mode}'
    )

    # Notify all servers that new state is available (uwu)
    tasks.add_task(push_state_to_nodes, request.app, dinf)

    # For the front end, we want to make sure we have all the information before returning
    if query.do_full_infraction:
        if dinf.user is not None:
            await get_user_data(request.app, dinf.id, True)
        else:
            await discord_notify_create_infraction(request.app, dinf)
        if dinf.ip is not None:
            await get_vpn_data(request.app, dinf.id, True)

        # Refetch this!
        dinf = await DInfraction.from_id(request.app.state.db[MONGO_DB], dinf.id)
    else:
        # Schedule a background task to add in missing details (like VPN check + profile / name)
        if dinf.user is not None:
            tasks.add_task(get_user_data, request.app, dinf.id, True)
        else:
            tasks.add_task(discord_notify_create_infraction, request.app, dinf)
        if dinf.ip is not None:
            tasks.add_task(get_vpn_data, request.app, dinf.id, True)

    return await as_infraction(request.app, dinf, should_include_ip(auth[0], auth[2]))


@infraction_router.post(
    '/using_policy',
    response_model=Infraction,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    dependencies=[Depends(csrf_protect)],
)
async def create_infraction_from_policy(
    request: Request,
    query: CreateInfractionUsingPolicy,
    tasks: BackgroundTasks,
    auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access),
):
    if auth[0] == NOT_AUTHED_USER:
        raise HTTPException(detail='This route requires authorization.', status_code=401)

    acting_admin, acting_admin_id = await get_acting(request, query.admin, auth[0], auth[1])

    server_ov = None

    if query.server is not None:
        if auth[2] & PERMISSION_ASSIGN_TO_SERVER != PERMISSION_ASSIGN_TO_SERVER:
            raise HTTPException(detail='Insufficient permissions to override the server', status_code=403)

        server_ov = ObjectId(query.server)

    if query.player.gs_id and query.allow_normalize:
        query.player.gs_id = await normalize_id(request.app, query.player.gs_service, query.player.gs_id)

    dinf = await create_dinfraction_with_policy(
        request.app,
        auth[0],
        player=query.player,
        scope=query.scope,
        policy_id=query.policy_id,
        admin=acting_admin_id,
        reason_override=query.reason,
        actor_id=auth[1],
        other_pol=query.consider_other_policies,
        server_override=server_ov,
    )

    rp = get_permissions(dinf)

    if acting_admin.permissions & rp != rp or auth[2] & rp != rp:
        raise HTTPException(detail='Insufficient privileges', status_code=403)

    aa = acting_admin if acting_admin.mongo_admin_id is not None else None

    if await check_immunity(request.app, dinf, aa):
        raise HTTPException(detail='Your target is immune', status_code=403)

    # Write the dinfraction
    await dinf.commit(request.app.state.db[MONGO_DB])

    # Notify all servers that new state is available (uwu)
    tasks.add_task(push_state_to_nodes, request.app, dinf)

    # For the front end, we want to make sure we have all the information before returning
    if query.do_full_infraction:
        if dinf.user is not None:
            await get_user_data(request.app, dinf.id, True)
        if dinf.ip is not None:
            await get_vpn_data(request.app, dinf.id, True)

        # Refetch this!
        dinf = await DInfraction.from_id(request.app.state.db[MONGO_DB], dinf.id)
    else:
        # Schedule a background task to add in missing details (like VPN check + profile / name)
        if dinf.user is not None:
            tasks.add_task(get_user_data, request.app, dinf.id, True)
        if dinf.ip is not None:
            tasks.add_task(get_vpn_data, request.app, dinf.id, True)

    # Create audit log entry
    daudit = DAuditLog(
        time=datetime.now(tz=UTC),
        event_type=EVENT_NEW_INFRACTION,
        initiator=acting_admin.mongo_admin_id,
        key_pair=(auth[0], auth[1]),
        message=f'{acting_admin.name} ({acting_admin.ips_id}) created an infraction {dinf.id} with flags'
        f' {dinf.flags} on {user_str(dinf)}',
    )

    await daudit.commit(request.app.state.db[MONGO_DB])

    logger.info(
        f'{acting_admin.name} ({acting_admin.ips_id}) created an infraction {dinf.id} with flags {dinf.flags}'
        f' on {user_str(dinf)}'
    )

    return await as_infraction(request.app, dinf, should_include_ip(auth[0], auth[2]))


def _i2p(dinf: DInfraction):
    puns = []

    for ps, pm in str2pflag.items():
        if dinf.flags & pm == pm:
            puns.append(ps)

    return puns


@infraction_router.post(
    '/remove',
    response_model=RemoveInfractionsOfPlayerReply,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    dependencies=[Depends(csrf_protect)],
)
async def remove_infraction(
    request: Request,
    query: RemoveInfractionsOfPlayer,
    tasks: BackgroundTasks,
    auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access),
):
    if auth[0] == NOT_AUTHED_USER:
        raise HTTPException(detail='This route requires authorization', status_code=401)

    acting_admin, acting_admin_id = await get_acting(request, query.admin, auth[0], auth[1])

    if (
        acting_admin.permissions & PERMISSION_CREATE_INFRACTION != PERMISSION_CREATE_INFRACTION
        and acting_admin.permissions & PERMISSION_EDIT_ALL_INFRACTIONS != PERMISSION_EDIT_ALL_INFRACTIONS
    ) or (
        auth[2] & PERMISSION_EDIT_ALL_INFRACTIONS != PERMISSION_EDIT_ALL_INFRACTIONS
        and auth[2] & PERMISSION_CREATE_INFRACTION != PERMISSION_CREATE_INFRACTION
    ):
        raise HTTPException(detail='You do not have permission to do this!', status_code=403)

    q = build_query_dict(
        auth[0],
        auth[1],
        gs_service=query.player.gs_service,
        gs_id=query.player.gs_id,
        ip=query.player.ip,
        ignore_others=not query.include_other_servers,
        active_only=True,
    )

    n_considered, n_skipped, n_removed, m = 0, 0, 0, 0

    async for dinf in DInfraction.from_query(request.app.state.db[MONGO_DB], q):
        # They might not have permission to remove others here...
        n_considered += 1
        if dinf.admin != acting_admin_id and (
            acting_admin.permissions & PERMISSION_EDIT_ALL_INFRACTIONS != PERMISSION_EDIT_ALL_INFRACTIONS
            or auth[2] & PERMISSION_EDIT_ALL_INFRACTIONS != PERMISSION_EDIT_ALL_INFRACTIONS
        ):
            n_skipped += 1
            continue
        n_removed += 1

        # If none of the types that we want are present in the infraction, we can just skip w/o db updates
        if query.restrict_types:
            found = False
            for t in query.restrict_types:
                if dinf.flags & str2pflag[t] == str2pflag[t]:
                    found = True
                    m += 1

            if not found:
                n_removed -= 1
                n_skipped += 1
                continue

        try:
            punishments = _i2p(dinf)
            # If there are less matches than there are punishments, we must instead remove punishments
            if query.restrict_types and m < len(punishments):
                for t in query.restrict_types:
                    punishments.remove(t)

                await modify_infraction(
                    request.app, dinf.id, reuse_dinf=dinf, punishments=punishments, actor=acting_admin_id
                )
            else:
                await modify_infraction(
                    request.app,
                    dinf.id,
                    set_removal_state=True,
                    removal_reason=query.remove_reason,
                    removed_by=acting_admin_id,
                    reuse_dinf=dinf,
                    actor=acting_admin_id,
                )

            # Notify all servers that new state is available (uwu)
            tasks.add_task(push_state_to_nodes, request.app, dinf)
        except ValueError:
            logger.error(f'Generated modify of {dinf.id} was invalid', exc_info=True)
            n_removed -= 1
            n_skipped += 1
            continue

        except Exception as e:
            logger.error(f'Removal of {dinf.id} failed', exc_info=e)
            n_removed -= 1
            n_skipped += 1
            continue

        daudit = DAuditLog(
            time=datetime.now(tz=UTC),
            event_type=EVENT_REMOVE_INFRACTION,
            initiator=acting_admin.mongo_admin_id,
            key_pair=(auth[0], auth[1]),
            message=f'{acting_admin.name} ({acting_admin.ips_id}) removed an infraction {dinf.id} '
            f' for {query.remove_reason}',
        )
        await daudit.commit(request.app.state.db[MONGO_DB])

        logger.info(
            f'{acting_admin.name} ({acting_admin.ips_id}) removed an infraction {dinf.id} '
            f' for {query.remove_reason}'
        )

    return RemoveInfractionsOfPlayerReply(num_removed=n_removed, num_considered=n_considered, num_not_removed=n_skipped)


@infraction_router.patch(
    '/{infraction_id}',
    response_model=Infraction,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    dependencies=[Depends(csrf_protect)],
)
async def edit_infraction(
    request: Request,
    infraction_id: str,
    query: ModifyInfraction,
    tasks: BackgroundTasks,
    auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access),
):
    if auth[0] == NOT_AUTHED_USER:
        raise HTTPException(detail='This route requires authorization', status_code=401)

    acting_admin, acting_admin_id = await get_acting(request, query.admin, auth[0], auth[1])

    # Load the DInfraction
    dinf = await DInfraction.from_id(request.app.state.db[MONGO_DB], infraction_id)

    if dinf is None:
        raise HTTPException(detail=f'Infraction {infraction_id} does not exist.', status_code=404)

    if not (
        acting_admin.permissions & PERMISSION_EDIT_ALL_INFRACTIONS == PERMISSION_EDIT_ALL_INFRACTIONS
        or (
            dinf.admin == acting_admin_id
            and acting_admin.permissions & PERMISSION_CREATE_INFRACTION == PERMISSION_CREATE_INFRACTION
        )
    ):
        raise HTTPException(detail='You do not have permission to edit this infraction.', status_code=403)

    if query.punishments is not None:
        # Changing a punishment type they dont have access to. Just ignore and keep as status already saved in database
        if acting_admin.permissions & PERMISSION_BLOCK_VOICE != PERMISSION_BLOCK_VOICE:
            adding_punishment = 'voice_block' in query.punishments
            if adding_punishment and dinf.flags & INFRACTION_VOICE_BLOCK != INFRACTION_VOICE_BLOCK:
                query.punishments.remove('voice_block')
            elif not adding_punishment and dinf.flags & INFRACTION_VOICE_BLOCK == INFRACTION_VOICE_BLOCK:
                query.punishments.append('voice_block')

        if acting_admin.permissions & PERMISSION_BLOCK_CHAT != PERMISSION_BLOCK_CHAT:
            adding_punishment = 'chat_block' in query.punishments
            if adding_punishment and dinf.flags & INFRACTION_CHAT_BLOCK != INFRACTION_CHAT_BLOCK:
                query.punishments.remove('chat_block')
            elif not adding_punishment and dinf.flags & INFRACTION_CHAT_BLOCK == INFRACTION_CHAT_BLOCK:
                query.punishments.append('chat_block')

        if acting_admin.permissions & PERMISSION_BAN != PERMISSION_BAN:
            adding_punishment = 'ban' in query.punishments
            if adding_punishment and dinf.flags & INFRACTION_BAN != INFRACTION_BAN:
                query.punishments.remove('ban')
            elif not adding_punishment and dinf.flags & INFRACTION_BAN == INFRACTION_BAN:
                query.punishments.append('ban')

        if acting_admin.permissions & PERMISSION_ADMIN_CHAT_BLOCK != PERMISSION_ADMIN_CHAT_BLOCK:
            adding_punishment = 'admin_chat_block' in query.punishments
            if adding_punishment and dinf.flags & INFRACTION_ADMIN_CHAT_BLOCK != INFRACTION_ADMIN_CHAT_BLOCK:
                query.punishments.remove('admin_chat_block')
            elif not adding_punishment and dinf.flags & INFRACTION_ADMIN_CHAT_BLOCK == INFRACTION_ADMIN_CHAT_BLOCK:
                query.punishments.append('admin_chat_block')

        if acting_admin.permissions & PERMISSION_CALL_ADMIN_BLOCK != PERMISSION_CALL_ADMIN_BLOCK:
            adding_punishment = 'call_admin_block' in query.punishments
            if adding_punishment and dinf.flags & INFRACTION_CALL_ADMIN_BAN != INFRACTION_CALL_ADMIN_BAN:
                query.punishments.remove('call_admin_block')
            elif not adding_punishment and dinf.flags & INFRACTION_CALL_ADMIN_BAN == INFRACTION_CALL_ADMIN_BAN:
                query.punishments.append('call_admin_block')

        if acting_admin.permissions & PERMISSION_BLOCK_ITEMS != PERMISSION_BLOCK_ITEMS:
            adding_punishment = 'item_block' in query.punishments
            if adding_punishment and dinf.flags & INFRACTION_ITEM_BLOCK != INFRACTION_ITEM_BLOCK:
                query.punishments.remove('item_block')
            elif not adding_punishment and dinf.flags & INFRACTION_ITEM_BLOCK == INFRACTION_ITEM_BLOCK:
                query.punishments.append('item_block')

    a = query.admin

    if query.admin is not None and isinstance(query.admin, Initiator):
        adm = await load_admin(request, query.admin)
        a = adm.mongo_admin_id

    b = query.policy_id

    if b is not None and isinstance(b, str):
        b = ObjectId(b)

    c = query.removed_by

    if c is not None and isinstance(c, Initiator):
        adm = await load_admin(request, query.removed_by)
        c = adm.mongo_admin_id
    elif query.set_removal_state and c is None and auth[0] == AUTHED_USER:
        c = auth[1]

    try:
        await modify_infraction(
            app=request.app,
            target=dinf.id,
            author=a,
            make_session=query.make_session,
            make_permanent=query.make_permanent,
            expiration=query.expiration,
            time_left=query.time_left,
            policy_id=b,
            make_web=query.make_web,
            server=obj_id(query.server),
            reason=query.reason,
            set_removal_state=query.set_removal_state,
            removed_by=c,
            removal_reason=query.removal_reason,
            punishments=query.punishments,
            scope=query.scope,
            vpn=query.vpn,
            reuse_dinf=dinf,
            actor=acting_admin_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    daudit = DAuditLog(
        time=datetime.now(tz=UTC),
        event_type=EVENT_EDIT_INFRACTION,
        initiator=acting_admin.mongo_admin_id,
        key_pair=(auth[0], auth[1]),
        message=f'{acting_admin.name} ({acting_admin.ips_id}) edited an infraction {dinf.id}',
        long_msg=query.json(exclude_defaults=True, exclude_none=True, exclude_unset=True),
    )

    await daudit.commit(request.app.state.db[MONGO_DB])

    logger.info(f'{acting_admin.name} ({acting_admin.ips_id}) edited an infraction {dinf.id}')

    # Notify all servers that new state is available (uwu)
    tasks.add_task(push_state_to_nodes, request.app, dinf)

    return await as_infraction(request.app, dinf, should_include_ip(auth[0], auth[2]))


@infraction_router.post(
    '/{infraction_id}/comment',
    response_model=Infraction,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    dependencies=[Depends(csrf_protect)],
)
async def add_comment(
    request: Request,
    infraction_id: str,
    query: AddComment,
    auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access),
):
    if auth[0] == NOT_AUTHED_USER:
        raise HTTPException(detail='You must be logged in to do this!', status_code=401)

    acting_admin, acting_admin_id = await get_acting(request, query.admin, auth[0], auth[1])

    if (
        acting_admin.permissions & PERMISSION_COMMENT != PERMISSION_COMMENT
        or auth[2] & PERMISSION_COMMENT != PERMISSION_COMMENT
    ):
        raise HTTPException(detail='You do not have permission to do this!', status_code=403)

    dinf = await DInfraction.from_id(request.app.state.db[MONGO_DB], infraction_id)

    if dinf is None:
        raise HTTPException(detail='No such infraction exists!', status_code=404)

    query.content = filter_badchars(query.content)

    dc = DComment(
        content=query.content, author=acting_admin_id, private=query.set_private, created=datetime.now(tz=UTC)
    )

    await dinf.append_to_array_field(request.app.state.db[MONGO_DB], 'comments', dc)

    daudit = DAuditLog(
        time=datetime.now(tz=UTC),
        event_type=EVENT_NEW_COMMENT,
        initiator=acting_admin.mongo_admin_id,
        key_pair=(auth[0], auth[1]),
        message=f'{acting_admin.name} added a comment to {str_id(dinf.id)} with content ' f'{query.content}',
    )

    await daudit.commit(request.app.state.db[MONGO_DB])

    logger.info(f'{acting_admin.name} added a comment to {str_id(dinf.id)} with content {query.content}')

    return await as_infraction(request.app, dinf, should_include_ip(auth[0], auth[2]))


# Same function since they're so similar
async def _update_or_delete_comment(
    request: Request,
    infraction_id: str,
    query: Union[EditComment, DeleteComment],
    auth: Tuple[int, Optional[ObjectId], int],
):
    if auth[0] == NOT_AUTHED_USER:
        raise HTTPException(detail='You must be logged in to do this!', status_code=401)

    acting_admin, acting_admin_id = await get_acting(request, query.admin, auth[0], auth[1])

    dinf = await DInfraction.from_id(request.app.state.db[MONGO_DB], infraction_id)

    if dinf is None:
        raise HTTPException(detail='No such infraction exists!', status_code=404)

    try:
        if (
            acting_admin.permissions & PERMISSION_COMMENT != PERMISSION_COMMENT
            or dinf.comments[query.comment_index].author != acting_admin_id
            or auth[2] & PERMISSION_COMMENT != PERMISSION_COMMENT
        ) and (
            acting_admin.permissions & PERMISSION_WEB_MODERATOR != PERMISSION_WEB_MODERATOR
            or auth[2] & PERMISSION_WEB_MODERATOR != PERMISSION_WEB_MODERATOR
        ):
            raise HTTPException(detail='You do not have permission to do that!', status_code=403)

        if isinstance(query, DeleteComment):
            das = (
                f'{acting_admin.name} deleted a comment from {dinf.id}. The content was'
                f' {dinf.comments[query.comment_index].content}'
            )
            del dinf.comments[query.comment_index]
        else:
            query.content = filter_badchars(query.content)
            das = (
                f'{acting_admin.name} edited a comment from {dinf.id}. The content was changed from '
                f' {dinf.comments[query.comment_index].content} to {query.content}'
            )
            dinf.comments[query.comment_index].content = query.content
            dinf.comments[query.comment_index].edit_data = {'time': datetime.now(tz=UTC)}

            if acting_admin_id is not None:
                dinf.comments[query.comment_index].edit_data['admin'] = acting_admin_id
    except IndexError:
        raise HTTPException(detail='There is no comment at that index', status_code=404)

    dc = dinf.comments

    await dinf.update_field(request.app.state.db[MONGO_DB], 'comments', dc)

    at = EVENT_EDIT_COMMENT if isinstance(query, EditComment) else EVENT_DELETE_COMMENT

    daudit = DAuditLog(
        time=datetime.now(tz=UTC),
        event_type=at,
        initiator=acting_admin.mongo_admin_id,
        key_pair=(auth[0], auth[1]),
        message=das,
    )

    await daudit.commit(request.app.state.db[MONGO_DB])

    logger.info(das)

    return await as_infraction(request.app, dinf, should_include_ip(auth[0], auth[2]))


@infraction_router.patch(
    '/{infraction_id}/comment',
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    dependencies=[Depends(csrf_protect)],
)
async def edit_comment(
    request: Request,
    infraction_id: str,
    query: EditComment,
    auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access),
):
    return await _update_or_delete_comment(request, infraction_id, query, auth)


@infraction_router.delete(
    '/{infraction_id}/comment',
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    dependencies=[Depends(csrf_protect)],
)
async def delete_comment(
    request: Request,
    infraction_id: str,
    query: DeleteComment,
    auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access),
):
    return await _update_or_delete_comment(request, infraction_id, query, auth)


@infraction_router.post(
    '/{infraction_id}/attachment/{filename}',
    response_model=FileInfo,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    dependencies=[Depends(csrf_protect)],
)
async def add_attachment(
    request: Request,
    infraction_id: str,
    filename: str,
    x_set_private: bool = Header(False),
    auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access),
):
    if auth[0] == NOT_AUTHED_USER:
        raise HTTPException(detail='You must be logged in to do this!', status_code=401)

    acting_admin, acting_admin_id = await get_acting(request, None, auth[0], auth[1])

    if (
        acting_admin.permissions & PERMISSION_ATTACH_FILE != PERMISSION_ATTACH_FILE
        or auth[2] & PERMISSION_ATTACH_FILE != PERMISSION_ATTACH_FILE
    ):
        raise HTTPException(detail='You do not have permission to do this!', status_code=403)

    if 'Content-Length' not in request.headers or int(request.headers['Content-Length']) > 30 * 1024 * 1024:
        raise HTTPException(detail="File is too large or request doesn't specify content length", status_code=413)

    dinf = await DInfraction.from_id(request.app.state.db[MONGO_DB], infraction_id)

    if dinf is None:
        raise HTTPException(detail='There is no such infraction.', status_code=404)

    gfs = AsyncIOMotorGridFSBucket(database=request.app.state.db[MONGO_DB])

    fis = request.stream()

    grid_in = gfs.open_upload_stream(slugify(filename), metadata={'content-type': 'application/octet-stream'})

    async for chk in fis:
        await grid_in.write(chk)

    await grid_in.close()

    file_id = grid_in._id

    dfile = DFile(
        gridfs_file=str(file_id),
        file_name=slugify(filename),
        uploaded_by=acting_admin_id,
        private=x_set_private,
        created=datetime.now(tz=UTC),
    )

    await dinf.append_to_array_field(request.app.state.db[MONGO_DB], 'files', dfile)

    das = (
        f'{acting_admin.name} uploaded a new file {slugify(filename)} ({file_id}) to infraction {dinf.id} with size'
        f' {request.headers["Content-Length"]}'
    )

    daudit = DAuditLog(
        time=datetime.now(tz=UTC),
        event_type=EVENT_UPLOAD_FILE,
        initiator=acting_admin.mongo_admin_id,
        key_pair=(auth[0], auth[1]),
        message=das,
    )

    await daudit.commit(request.app.state.db[MONGO_DB])

    logger.info(das)

    return FileInfo(
        name=slugify(filename), file_id=str(file_id), uploaded_by=acting_admin.ips_id, private=x_set_private
    )


@infraction_router.delete(
    '/{infraction_id}/attachment',
    response_model=Infraction,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    dependencies=[Depends(csrf_protect)],
)
async def delete_attachment(
    request: Request,
    infraction_id: str,
    query: DeleteFile,
    auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access),
):
    if auth[0] == NOT_AUTHED_USER:
        raise HTTPException(detail='You must be logged in to do this!', status_code=401)

    acting_admin, acting_admin_id = await get_acting(request, query.admin, auth[0], auth[1])

    dinf = await DInfraction.from_id(request.app.state.db[MONGO_DB], infraction_id)

    if dinf is None:
        raise HTTPException(detail='No such infraction was found in the database', status_code=404)

    try:
        dinf.files[query.file_idx]
    except IndexError:
        raise HTTPException(detail='No such file in the specified infraction exists', status_code=404)

    if (
        acting_admin.permissions & PERMISSION_ATTACH_FILE != PERMISSION_ATTACH_FILE
        or dinf.files[query.file_idx].uploaded_by != acting_admin_id
        or auth[2] & PERMISSION_ATTACH_FILE != PERMISSION_ATTACH_FILE
    ) and (
        acting_admin.permissions & PERMISSION_WEB_MODERATOR != PERMISSION_WEB_MODERATOR
        or auth[2] & PERMISSION_WEB_MODERATOR != PERMISSION_WEB_MODERATOR
    ):
        raise HTTPException(detail='You do not have permission to do that!', status_code=403)

    # Delete backend file object
    await AsyncIOMotorGridFSBucket(database=request.app.state.db[MONGO_DB]).delete(
        ObjectId(dinf.files[query.file_idx].gridfs_file)
    )

    # Unlink from dinf
    dfiles = dinf.files
    del dfiles[query.file_idx]
    await dinf.update_field(request.app.state.db[MONGO_DB], 'files', dfiles)

    das = f'{acting_admin.name} deleted file from infraction {dinf.id}'

    daudit = DAuditLog(
        time=datetime.now(tz=UTC),
        event_type=EVENT_UPLOAD_FILE,
        initiator=acting_admin.mongo_admin_id,
        key_pair=(auth[0], auth[1]),
        message=das,
    )

    await daudit.commit(request.app.state.db[MONGO_DB])

    logger.info(das)

    return await as_infraction(request.app, dinf, should_include_ip(auth[0], auth[2]))
