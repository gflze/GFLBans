import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Set, Tuple, Union

import bson
from bson import ObjectId
from dateutil.tz import UTC
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import ORJSONResponse
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from pymongo import DESCENDING
from starlette.background import BackgroundTasks
from starlette.requests import Request

from gflbans.api.auth import AuthInfo, check_access, csrf_protect
from gflbans.api_util import (
    as_infraction,
    construct_ci_resp,
    exclude_private_comments,
    obj_id,
    should_include_ip,
    str_id,
    user_str,
)
from gflbans.internal.config import AUTO_STACK_MAX_AGE, AUTO_STACK_MULTIPLIER, AUTO_STACK_START_TIME, MONGO_DB
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
from gflbans.internal.errors import SearchError
from gflbans.internal.flags import (
    INFRACTION_ADMIN_CHAT_BLOCK,
    INFRACTION_BAN,
    INFRACTION_CALL_ADMIN_BAN,
    INFRACTION_CHAT_BLOCK,
    INFRACTION_ITEM_BLOCK,
    INFRACTION_PERMANENT,
    INFRACTION_PLAYTIME_DURATION,
    INFRACTION_SESSION,
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
    PERMISSION_SCOPE_GLOBAL,
    PERMISSION_WEB_MODERATOR,
    str2pflag,
)
from gflbans.internal.infraction_utils import (
    check_immunity,
    create_dinfraction,
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
from gflbans.internal.models.api import FileInfo, Infraction, Initiator
from gflbans.internal.models.protocol import (
    AddComment,
    CheckInfractions,
    CheckInfractionsReply,
    CreateInfraction,
    DeleteComment,
    DeleteFile,
    EditComment,
    GetInfractions,
    GetInfractionsReply,
    InfractionStatisticsReply,
    ModifyInfraction,
    RecursiveSearch,
    RemoveInfractionsOfPlayer,
    RemoveInfractionsOfPlayerReply,
    Search,
)
from gflbans.internal.pyapi_utils import get_acting, load_admin
from gflbans.internal.search import contains_str, do_infraction_search
from gflbans.internal.utils import slugify

infraction_router = APIRouter(default_response_class=ORJSONResponse)


@infraction_router.get(
    '/', response_model=GetInfractionsReply, response_model_exclude_unset=True, response_model_exclude_none=True
)
async def get_infractions(
    request: Request,
    query: GetInfractions = Depends(GetInfractions),
    load_fast: bool = True,
    auth: AuthInfo = Depends(check_access),
):
    incl_ip = should_include_ip(auth.type, auth.permissions)  # Check if we have perms to see IP addresses

    ip = query.ip if incl_ip else None  # If we do not have permissions, force this value to None

    q = build_query_dict(
        auth.type,
        str_id(auth.authenticator_id),
        gs_service=query.player.gs_service,
        gs_id=query.player.gs_id,
        ip=ip,
        ignore_others=(not query.include_other_servers),
        active_only=query.active_only,
    )

    exclude_priv_comments = exclude_private_comments(auth.type, auth.permissions)
    infs = []

    async for dinf in DInfraction.from_query(
        request.app.state.db[MONGO_DB], q, limit=query.limit, skip=query.skip, sort=('created', DESCENDING)
    ):
        if load_fast:
            dinf.comments = []
            dinf.files = []
        infs.append(await as_infraction(request.app, dinf, incl_ip, exclude_priv_comments))

    return GetInfractionsReply(results=infs, total_matched=await DInfraction.count(request.app.state.db[MONGO_DB], q))


@infraction_router.get(
    '/{infraction_id}/info',
    response_model=Infraction,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def get_infraction(request: Request, infraction_id: str, auth: AuthInfo = Depends(check_access)):
    try:
        inf = await DInfraction.from_id(request.app.state.db[MONGO_DB], infraction_id)
    except bson.errors.InvalidId:
        raise HTTPException(detail='Invalid id', status_code=400)

    if inf is None:
        raise HTTPException(detail='No such infraction', status_code=404)

    return await as_infraction(
        request.app,
        inf,
        should_include_ip(auth.type, auth.permissions),
        exclude_private_comments(auth.type, auth.permissions),
    )


MAX_UNIX_TIMESTAMP = int((datetime.now() + timedelta(days=365 * 100)).timestamp())


@infraction_router.get(
    '/search', response_model=GetInfractionsReply, response_model_exclude_unset=True, response_model_exclude_none=True
)
async def search_infractions(
    request: Request,
    query: Search = Depends(Search),
    load_fast: bool = True,
    auth: AuthInfo = Depends(check_access),
):
    incl_ip = should_include_ip(auth.type, auth.permissions)

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

        infs.append(
            await as_infraction(request.app, dinf, incl_ip, exclude_private_comments(auth.type, auth.permissions))
        )

    return GetInfractionsReply(results=infs, total_matched=await DInfraction.count(request.app.state.db[MONGO_DB], cq))


async def recursive_infraction_search(
    app,
    ips: List[str],
    steam_ids: List[str],
    depth: int,
    visited_ids: Set[str],
    found_infractions: Set[str],
    limit: int,
    skip: int,
    load_fast: bool,
) -> List[DInfraction]:
    if depth <= 0 or (not ips and not steam_ids):
        return []

    # Remove already visited IPs and Steam IDs to prevent redundant searches
    ips = [ip for ip in ips if ip not in visited_ids]
    steam_ids = [sid for sid in steam_ids if sid not in visited_ids]

    if not ips and not steam_ids:
        return []

    visited_ids.update(ips)
    visited_ids.update(steam_ids)

    search_queries = []

    for ip in ips:
        search_queries.append(
            do_infraction_search(app, RecursiveSearch(ip=ip, gs_id=None, limit=limit, skip=skip), include_ip=True)
        )

    for steam_id in steam_ids:
        search_queries.append(
            do_infraction_search(app, RecursiveSearch(ip=None, gs_id=steam_id, limit=limit, skip=skip), include_ip=True)
        )

    # Generate all MongoDB search queries concurrently
    query_results = await asyncio.gather(*search_queries)

    # Flatten the results into a single MongoDB `$or` query
    search_query = {'$or': query_results} if len(query_results) > 1 else query_results[0]

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

        # Normalize excessive expiration times
        if dinf.expires is not None and dinf.expires > MAX_UNIX_TIMESTAMP:
            dinf.expires = None

        infractions.append(dinf)

        # Collect new identifiers for the next recursion batch
        if dinf.user and dinf.user.gs_id and dinf.user.gs_id not in visited_ids:
            new_steam_ids.add(dinf.user.gs_id)

        if dinf.ip and dinf.ip not in visited_ids:
            new_ips.add(dinf.ip)

    # Recursively search with all newly found identifiers in a **single batch**
    new_results = await recursive_infraction_search(
        app, list(new_ips), list(new_steam_ids), depth - 1, visited_ids, found_infractions, limit, skip, load_fast
    )

    infractions.extend(new_results)
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
    auth: AuthInfo = Depends(check_access),
):
    incl_ip = should_include_ip(auth.type, auth.permissions)
    # If we do not have permission to view IP, force it to None
    ip = query.ip if incl_ip else None

    if not ip and not query.gs_id:
        raise HTTPException(status_code=400, detail="At least one of 'ip' or 'gs_id' must be provided.")

    visited_ids = set()
    found_infractions = set()

    infractions = await recursive_infraction_search(
        request.app,
        [ip] if ip else [],
        [query.gs_id] if query.gs_id else [],
        query.depth,
        visited_ids,
        found_infractions,
        query.limit,
        query.skip,
        load_fast,
    )

    if query.limit == 0:
        return GetInfractionsReply(results=[], total_matched=len(infractions))

    # Sort by `created` timestamp (descending order: newest first)
    sorted_infractions = sorted(infractions, key=lambda inf: inf.created, reverse=True)

    # Apply skip and limit
    paginated_infractions = sorted_infractions[query.skip : query.skip + query.limit]

    exclude_priv_comments = exclude_private_comments(auth.type, auth.permissions)

    return GetInfractionsReply(
        results=[
            await as_infraction(request.app, inf, incl_ip, exclude_priv_comments) for inf in paginated_infractions
        ],
        total_matched=len(infractions),  # Total before pagination
    )


@infraction_router.get(
    '/check', response_model=CheckInfractionsReply, response_model_exclude_unset=True, response_model_exclude_none=True
)
async def check_infractions(
    request: Request,
    query: CheckInfractions = Depends(CheckInfractions),
    auth: AuthInfo = Depends(check_access),
):
    incl_ip = should_include_ip(auth.type, auth.permissions)  # Check if we have perms to see IP addresses

    ip = query.ip if incl_ip else None  # If we do not have permissions, force this value to None

    if ip is None and query.player is None:
        raise HTTPException(detail='Cannot have both an empty ip and an empty player', status_code=401)

    # run a vpn check
    # do not check by IP if it is a VPN
    # if ip:
    #     vpn_result = await check_vpn(request.app, ip)
    #
    #     if vpn_result == VPN_YES or vpn_result == VPN_DUBIOUS:
    #         ip = None

    q = build_query_dict(
        auth.type,
        str_id(auth.authenticator_id),
        gs_service=query.player.gs_service,
        gs_id=query.player.gs_id,
        ip=ip,
        ignore_others=(not query.include_other_servers),
        active_only=True,
    )

    ci_resp = await construct_ci_resp(request.app.state.db[MONGO_DB], q)

    return ci_resp


async def find_longest_infraction_duration(app, query) -> Optional[int]:
    longest = None
    async for dinf in DInfraction.from_query(app.state.db[MONGO_DB], query, sort=('created', DESCENDING)):
        if (
            longest == 0
            or dinf.flags & INFRACTION_PERMANENT == INFRACTION_PERMANENT
            or (dinf.expires is not None and dinf.expires > MAX_UNIX_TIMESTAMP)
        ):
            longest = 0
        elif dinf.flags & INFRACTION_SESSION == INFRACTION_SESSION and longest is None:
            longest = -1
        elif dinf.original_time is not None:
            longest = dinf.original_time if longest is None else max(dinf.original_time, longest)
        elif dinf.expires is not None and dinf.created is not None:
            total_time = dinf.expires - dinf.created
            longest = total_time if longest is None else max(total_time, longest)

    return longest


@infraction_router.get(
    '/stats',
    response_model=InfractionStatisticsReply,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def infraction_stats(
    request: Request,
    query: CheckInfractions = Depends(CheckInfractions),
    auth: AuthInfo = Depends(check_access),
):
    ip = query.ip if should_include_ip(auth.type, auth.permissions) else None

    if ip is None and query.player is None:
        raise HTTPException(detail='Cannot have both an empty ip and an empty player', status_code=401)

    q = build_query_dict(
        auth.type,
        str_id(auth.authenticator_id),
        gs_service=query.player.gs_service,
        gs_id=query.player.gs_id,
        ip=ip,
        ignore_others=(not query.include_other_servers),
        active_only=query.active_only,
        exclude_removed=query.exclude_removed,
        playtime_based=query.playtime_based,
    )

    if query.reason is not None:
        q['reason'] = contains_str(query.reason)

    query_voice = {'$and': [q, {'flags': {'$bitsAllSet': INFRACTION_VOICE_BLOCK}}]}
    query_chat = {'$and': [q, {'flags': {'$bitsAllSet': INFRACTION_CHAT_BLOCK}}]}
    query_ban = {'$and': [q, {'flags': {'$bitsAllSet': INFRACTION_BAN}}]}
    query_admin_chat = {'$and': [q, {'flags': {'$bitsAllSet': INFRACTION_ADMIN_CHAT_BLOCK}}]}
    query_call_admin = {'$and': [q, {'flags': {'$bitsAllSet': INFRACTION_CALL_ADMIN_BAN}}]}
    query_item = {'$and': [q, {'flags': {'$bitsAllSet': INFRACTION_ITEM_BLOCK}}]}
    query_warning = {
        '$and': [
            q,
            {
                'flags': {
                    '$bitsAllClear': INFRACTION_CALL_ADMIN_BAN
                    | INFRACTION_ADMIN_CHAT_BLOCK
                    | INFRACTION_BAN
                    | INFRACTION_CHAT_BLOCK
                    | INFRACTION_VOICE_BLOCK
                    | INFRACTION_ITEM_BLOCK
                }
            },
        ]
    }

    stat_total = InfractionStatisticsReply(
        voice_block_count=0,
        text_block_count=0,
        ban_count=0,
        admin_chat_block_count=0,
        call_admin_block_count=0,
        item_block_count=0,
        warning_count=0,
    )

    tasks = [
        request.app.state.db[MONGO_DB].infractions.count_documents(query_voice),
        request.app.state.db[MONGO_DB].infractions.count_documents(query_chat),
        request.app.state.db[MONGO_DB].infractions.count_documents(query_ban),
        request.app.state.db[MONGO_DB].infractions.count_documents(query_admin_chat),
        request.app.state.db[MONGO_DB].infractions.count_documents(query_call_admin),
        request.app.state.db[MONGO_DB].infractions.count_documents(query_item),
        request.app.state.db[MONGO_DB].infractions.count_documents(query_warning),
    ]

    if not query.count_only:
        tasks.extend(
            [
                find_longest_infraction_duration(request.app, query_voice),
                find_longest_infraction_duration(request.app, query_chat),
                find_longest_infraction_duration(request.app, query_ban),
                find_longest_infraction_duration(request.app, query_admin_chat),
                find_longest_infraction_duration(request.app, query_call_admin),
                find_longest_infraction_duration(request.app, query_item),
                find_longest_infraction_duration(request.app, query_warning),
            ]
        )

    results = await asyncio.gather(*tasks)

    (
        stat_total.voice_block_count,
        stat_total.text_block_count,
        stat_total.ban_count,
        stat_total.admin_chat_block_count,
        stat_total.call_admin_block_count,
        stat_total.item_block_count,
        stat_total.warning_count,
    ) = results[:7]

    if not query.count_only:
        (
            stat_total.voice_block_longest,
            stat_total.text_block_longest,
            stat_total.ban_longest,
            stat_total.admin_chat_block_longest,
            stat_total.call_admin_block_longest,
            stat_total.item_block_longest,
            stat_total.warning_longest,
        ) = results[7:]

    return stat_total


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
    auth: AuthInfo = Depends(check_access),
):
    if auth.type == NOT_AUTHED_USER:
        raise HTTPException(detail='This route requires authorization.', status_code=401)

    acting_admin, acting_admin_id = await get_acting(request, query.admin, auth.type, auth.authenticator_id)

    # Server
    if query.server is not None:
        if auth.permissions & PERMISSION_ASSIGN_TO_SERVER != PERMISSION_ASSIGN_TO_SERVER:
            raise HTTPException(detail='Insufficient permissions to override the server', status_code=403)

        # If infraction is issued through a server and the admin cant issue global punishments,
        # just make the infraction server only
        if (
            auth.type == SERVER_KEY
            and query.scope == 'global'
            and query.admin is not None
            and acting_admin.permissions & PERMISSION_SCOPE_GLOBAL != PERMISSION_SCOPE_GLOBAL
        ):
            query.scope = 'server'

        server = ObjectId(query.server)
    elif auth.type == SERVER_KEY and auth.authenticator_id is not None:
        server = auth.authenticator_id
    else:
        server = None

    if query.player.gs_id and query.allow_normalize:
        query.player.gs_id = await normalize_id(request.app, query.player.gs_service, query.player.gs_id)

    duration_to_use = query.duration

    if query.auto_duration:
        # Base query
        q = build_query_dict(
            auth.type,
            str_id(auth.authenticator_id),
            gs_service=query.player.gs_service,
            gs_id=query.player.gs_id,
            ip=query.player.ip,
            ignore_others=False,
            active_only=False,
            exclude_removed=True,
            playtime_based=query.playtime_based,
        )

        if not query.playtime_based:
            q['flags']['$bitsAllClear'] = q['flags'].get('$bitsAllClear', 0) | INFRACTION_PLAYTIME_DURATION

        q['created'] = {'$gte': datetime.now(tz=UTC).timestamp() - AUTO_STACK_MAX_AGE}

        # Determine the combined punishment flag
        punishment_flag = 0
        for punishment in query.punishments:
            punishment_flag |= str2pflag.get(punishment, 0)

        q.setdefault('flags', {})

        if punishment_flag == 0:
            # Warning
            q['flags']['$bitsAllClear'] = q['flags'].get('$bitsAllClear', 0) | sum(str2pflag.values())
        else:
            q['flags']['$bitsAnySet'] = q['flags'].get('$bitsAnySet', 0) | punishment_flag

        # Get the previous longest duration
        longest = await find_longest_infraction_duration(request.app, q)

        # Decide the new duration
        if longest is None and query.duration:
            duration_to_use = query.duration
        elif longest is None or longest < 0:
            duration_to_use = AUTO_STACK_START_TIME
        elif longest == 0:
            duration_to_use = None  # Permanent
        else:
            duration_to_use = longest * AUTO_STACK_MULTIPLIER

    ten_years = 60 * 60 * 24 * 365 * 10
    if duration_to_use and duration_to_use > ten_years:
        duration_to_use = None  # Permanent

    dinf = create_dinfraction(
        player=query.player,
        reason=query.reason,
        scope=query.scope,
        punishments=query.punishments,
        session=query.session,
        created=query.created,
        duration=duration_to_use,
        admin=acting_admin_id,
        playtime_based=query.playtime_based,
        server=server,
    )

    rp = get_permissions(dinf)

    if (acting_admin.permissions & rp != rp and not query.import_mode) or auth.permissions & rp != rp:
        raise HTTPException(detail='Insufficient privileges', status_code=403)

    aa = acting_admin if acting_admin.mongo_admin_id is not None else None

    if await check_immunity(request.app, dinf, aa):
        raise HTTPException(detail='Your target is immune', status_code=403)

    # Write the dinfraction
    await dinf.commit(request.app.state.db[MONGO_DB])

    logger.info(
        f'{acting_admin.name} ({acting_admin.ips_id}) created an infraction {dinf.id} with flags {dinf.flags}'
        f' on {user_str(dinf)}, import_mode = {query.import_mode}'
    )

    # Create audit log entry
    await DAuditLog(
        time=datetime.now(tz=UTC).timestamp(),
        event_type=EVENT_NEW_INFRACTION,
        authentication_type=auth.type,
        authenticator=auth.authenticator_id,
        admin=auth.admin.mongo_admin_id if auth.admin else None,
        new_item=dinf.dict(),
    ).commit(request.app.state.db[MONGO_DB])

    # Notify all servers that new state is available (uwu)
    tasks.add_task(push_state_to_nodes, request.app, dinf)

    # For the front end, we want to make sure we have all the information before returning
    if query.do_full_infraction:
        if dinf.user is not None:
            await get_user_data(request.app, dinf.id, True, auth.type == SERVER_KEY)
        else:
            await discord_notify_create_infraction(request.app, dinf, auth.type == SERVER_KEY)
        if dinf.ip is not None:
            await get_vpn_data(request.app, dinf.id, True)

        # Refetch this!
        dinf = await DInfraction.from_id(request.app.state.db[MONGO_DB], dinf.id)
    else:
        # Schedule a background task to add in missing details (like VPN check + profile / name)
        if dinf.user is not None:
            tasks.add_task(get_user_data, request.app, dinf.id, True, auth.type == SERVER_KEY)
        else:
            tasks.add_task(discord_notify_create_infraction, request.app, dinf, auth.type == SERVER_KEY)
        if dinf.ip is not None:
            tasks.add_task(get_vpn_data, request.app, dinf.id, True)

    return await as_infraction(
        request.app,
        dinf,
        should_include_ip(auth.type, auth.permissions),
        exclude_private_comments(auth.type, auth.permissions),
    )


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
    auth: AuthInfo = Depends(check_access),
):
    if auth.type == NOT_AUTHED_USER:
        raise HTTPException(detail='This route requires authorization', status_code=401)

    acting_admin, acting_admin_id = await get_acting(request, query.admin, auth.type, auth.authenticator_id)

    if (
        acting_admin.permissions & PERMISSION_CREATE_INFRACTION != PERMISSION_CREATE_INFRACTION
        and acting_admin.permissions & PERMISSION_EDIT_ALL_INFRACTIONS != PERMISSION_EDIT_ALL_INFRACTIONS
    ) or (
        auth.permissions & PERMISSION_EDIT_ALL_INFRACTIONS != PERMISSION_EDIT_ALL_INFRACTIONS
        and auth.permissions & PERMISSION_CREATE_INFRACTION != PERMISSION_CREATE_INFRACTION
    ):
        raise HTTPException(detail='You do not have permission to do this!', status_code=403)

    q = build_query_dict(
        auth.type,
        auth.authenticator_id,
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
            or auth.permissions & PERMISSION_EDIT_ALL_INFRACTIONS != PERMISSION_EDIT_ALL_INFRACTIONS
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

        logger.info(
            f'{acting_admin.name} ({acting_admin.ips_id}) removed an infraction {dinf.id} '
            f' for {query.remove_reason}'
        )

        await DAuditLog(
            time=datetime.now(tz=UTC).timestamp(),
            event_type=EVENT_REMOVE_INFRACTION,
            authentication_type=auth.type,
            authenticator=auth.authenticator_id,
            admin=auth.admin.mongo_admin_id if auth.admin else None,
            old_item=dinf.dict(),
        ).commit(request.app.state.db[MONGO_DB])

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
    auth: AuthInfo = Depends(check_access),
):
    if auth.type == NOT_AUTHED_USER:
        raise HTTPException(detail='This route requires authorization', status_code=401)

    acting_admin, acting_admin_id = await get_acting(request, query.admin, auth.type, auth.authenticator_id)

    # Load the DInfraction
    dinf = await DInfraction.from_id(request.app.state.db[MONGO_DB], infraction_id)

    if dinf is None:
        raise HTTPException(detail=f'Infraction {infraction_id} does not exist.', status_code=404)

    original_dinf_info = dinf  # For Audit logging purposes

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

    c = query.removed_by

    if c is not None and isinstance(c, Initiator):
        adm = await load_admin(request, query.removed_by)
        c = adm.mongo_admin_id
    elif query.set_removal_state and c is None and auth.type == AUTHED_USER:
        c = auth.authenticator_id

    try:
        await modify_infraction(
            app=request.app,
            target=dinf.id,
            author=a,
            make_session=query.make_session,
            make_permanent=query.make_permanent,
            expiration=query.expiration,
            time_left=query.time_left,
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

    logger.info(f'{acting_admin.name} ({acting_admin.ips_id}) edited an infraction {dinf.id}')

    await DAuditLog(
        time=datetime.now(tz=UTC).timestamp(),
        event_type=EVENT_REMOVE_INFRACTION if query.set_removal_state else EVENT_EDIT_INFRACTION,
        authentication_type=auth.type,
        authenticator=auth.authenticator_id,
        admin=auth.admin.mongo_admin_id if auth.admin else None,
        new_item=dinf.dict(),
        old_item=original_dinf_info.dict(),
    ).commit(request.app.state.db[MONGO_DB])

    # Notify all servers that new state is available (uwu)
    tasks.add_task(push_state_to_nodes, request.app, dinf)

    return await as_infraction(
        request.app,
        dinf,
        should_include_ip(auth.type, auth.permissions),
        exclude_private_comments(auth.type, auth.permissions),
    )


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
    auth: AuthInfo = Depends(check_access),
):
    if auth.type == NOT_AUTHED_USER:
        raise HTTPException(detail='You must be logged in to do this!', status_code=401)

    acting_admin, acting_admin_id = await get_acting(request, query.admin, auth.type, auth.authenticator_id)

    if (
        acting_admin.permissions & PERMISSION_COMMENT != PERMISSION_COMMENT
        or auth.permissions & PERMISSION_COMMENT != PERMISSION_COMMENT
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

    logger.info(f'{acting_admin.name} added a comment to {str_id(dinf.id)} with content {query.content}')

    await DAuditLog(
        time=datetime.now(tz=UTC).timestamp(),
        event_type=EVENT_NEW_COMMENT,
        authentication_type=auth.type,
        authenticator=auth.authenticator_id,
        admin=auth.admin.mongo_admin_id if auth.admin else None,
        new_item=dc.dict(),
    ).commit(request.app.state.db[MONGO_DB])

    return await as_infraction(
        request.app,
        dinf,
        should_include_ip(auth.type, auth.permissions),
        exclude_private_comments(auth.type, auth.permissions),
    )


# Same function since they're so similar
async def _update_or_delete_comment(
    request: Request,
    infraction_id: str,
    query: Union[EditComment, DeleteComment],
    auth: Tuple[int, Optional[ObjectId], int],
):
    if auth.type == NOT_AUTHED_USER:
        raise HTTPException(detail='You must be logged in to do this!', status_code=401)

    acting_admin, acting_admin_id = await get_acting(request, query.admin, auth.type, auth.authenticator_id)

    dinf = await DInfraction.from_id(request.app.state.db[MONGO_DB], infraction_id)

    if dinf is None:
        raise HTTPException(detail='No such infraction exists!', status_code=404)

    original_dinf_info = dinf  # For Audit logging purposes

    try:
        if (
            acting_admin.permissions & PERMISSION_COMMENT != PERMISSION_COMMENT
            or dinf.comments[query.comment_index].author != acting_admin_id
            or auth.permissions & PERMISSION_COMMENT != PERMISSION_COMMENT
        ) and (
            acting_admin.permissions & PERMISSION_WEB_MODERATOR != PERMISSION_WEB_MODERATOR
            or auth.permissions & PERMISSION_WEB_MODERATOR != PERMISSION_WEB_MODERATOR
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

    logger.info(das)

    await DAuditLog(
        time=datetime.now(tz=UTC).timestamp(),
        event_type=EVENT_EDIT_COMMENT if isinstance(query, EditComment) else EVENT_DELETE_COMMENT,
        authentication_type=auth.type,
        authenticator=auth.authenticator_id,
        admin=auth.admin.mongo_admin_id if auth.admin else None,
        new_item=dinf.dict(),
        old_item=original_dinf_info.dict(),
    ).commit(request.app.state.db[MONGO_DB])

    return await as_infraction(
        request.app,
        dinf,
        should_include_ip(auth.type, auth.permissions),
        exclude_private_comments(auth.type, auth.permissions),
    )


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
    auth: AuthInfo = Depends(check_access),
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
    auth: AuthInfo = Depends(check_access),
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
    auth: AuthInfo = Depends(check_access),
):
    if auth.type == NOT_AUTHED_USER:
        raise HTTPException(detail='You must be logged in to do this!', status_code=401)

    acting_admin, acting_admin_id = await get_acting(request, None, auth.type, auth.authenticator_id)

    if (
        acting_admin.permissions & PERMISSION_ATTACH_FILE != PERMISSION_ATTACH_FILE
        or auth.permissions & PERMISSION_ATTACH_FILE != PERMISSION_ATTACH_FILE
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

    logger.info(
        f'{acting_admin.name} uploaded a new file {slugify(filename)} ({file_id}) to infraction {dinf.id} with size'
        f' {request.headers["Content-Length"]}'
    )

    await DAuditLog(
        time=datetime.now(tz=UTC).timestamp(),
        event_type=EVENT_UPLOAD_FILE,
        authentication_type=auth.type,
        authenticator=auth.authenticator_id,
        admin=auth.admin.mongo_admin_id if auth.admin else None,
        new_item=dfile.dict(),
    ).commit(request.app.state.db[MONGO_DB])

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
    auth: AuthInfo = Depends(check_access),
):
    if auth.type == NOT_AUTHED_USER:
        raise HTTPException(detail='You must be logged in to do this!', status_code=401)

    acting_admin, acting_admin_id = await get_acting(request, query.admin, auth.type, auth.authenticator_id)

    dinf = await DInfraction.from_id(request.app.state.db[MONGO_DB], infraction_id)

    if dinf is None:
        raise HTTPException(detail='No such infraction was found in the database', status_code=404)

    try:
        dinf.files[query.file_idx]
    except IndexError:
        raise HTTPException(detail='No such file in the specified infraction exists', status_code=404)

    old_item = dinf.files[query.file_idx]  # For Audit logging purposes

    if (
        acting_admin.permissions & PERMISSION_ATTACH_FILE != PERMISSION_ATTACH_FILE
        or dinf.files[query.file_idx].uploaded_by != acting_admin_id
        or auth.permissions & PERMISSION_ATTACH_FILE != PERMISSION_ATTACH_FILE
    ) and (
        acting_admin.permissions & PERMISSION_WEB_MODERATOR != PERMISSION_WEB_MODERATOR
        or auth.permissions & PERMISSION_WEB_MODERATOR != PERMISSION_WEB_MODERATOR
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

    logger.info(f'{acting_admin.name} deleted file from infraction {dinf.id}')

    await DAuditLog(
        time=datetime.now(tz=UTC).timestamp(),
        event_type=EVENT_UPLOAD_FILE,
        authentication_type=auth.type,
        authenticator=auth.authenticator_id,
        admin=auth.admin.mongo_admin_id if auth.admin else None,
        old_item=old_item.dict(),
    ).commit(request.app.state.db[MONGO_DB])

    return await as_infraction(
        request.app,
        dinf,
        should_include_ip(auth.type, auth.permissions),
        exclude_private_comments(auth.type, auth.permissions),
    )
