import asyncio
from contextlib import suppress
from datetime import datetime
from typing import List, Optional, Tuple

from bson import ObjectId
from dateutil.tz import UTC
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import PositiveInt
from pymongo import UpdateMany
from redis.exceptions import RedisError
from starlette.requests import Request

from gflbans.api.auth import check_access
from gflbans.api_util import construct_ci_resp
from gflbans.internal.asn import VPN_DUBIOUS, VPN_YES, check_location, check_vpn
from gflbans.internal.avatar import process_avatar
from gflbans.internal.config import MONGO_DB
from gflbans.internal.constants import NOT_AUTHED_USER, SERVER_KEY
from gflbans.internal.database.common import DFile
from gflbans.internal.database.infraction import DInfraction, build_query_dict
from gflbans.internal.database.server import DCallData, DServer, DServerInfo, DUserIP
from gflbans.internal.discord_calladmin import (
    claim_monitor_task,
    execute_claim,
    execute_webhook,
    prepare_calladmin_image,
)
from gflbans.internal.errors import NoSuchAdminError
from gflbans.internal.flags import (
    INFRACTION_CALL_ADMIN_BAN,
    INFRACTION_PLAYTIME_DURATION,
    PERMISSION_VPN_CHECK_SKIP,
)
from gflbans.internal.integrations.games import get_user_info
from gflbans.internal.integrations.games.steam import get_steam_multiple_user_info
from gflbans.internal.log import logger
from gflbans.internal.models.api import AdminInfo, Initiator, PlayerObjIPOptional, PlayerObjNoIp
from gflbans.internal.models.protocol import (
    CheckVPN,
    CheckVPNReply,
    ClaimCallAdmin,
    ClaimCallAdminReply,
    ExecuteCallAdmin,
    ExecuteCallAdminReply,
    Heartbeat,
    HeartbeatChange,
)
from gflbans.internal.pyapi_utils import load_admin_from_initiator
from gflbans.internal.utils import validate

gs_router = APIRouter()


async def _process_heartbeat_player(app, ply: PlayerObjIPOptional) -> DUserIP:
    avatar: Optional[DFile] = None
    name: str = 'Unknown Player'

    try:
        user_info = await get_user_info(app, ply.gs_service, ply.gs_id)
        name = user_info['name']
        avatar = DFile(**await process_avatar(app, user_info['avatar_url']))
    except Exception as e:
        logger.error('Failed to download avatar image or fetch user info.', exc_info=e)

    return DUserIP(**ply.dict(), gs_name=name, gs_avatar=avatar)


async def _process_heartbeat_multiple_players(app, ply_list: list[PlayerObjIPOptional]) -> list[DUserIP]:
    user_list = []
    steamid_list = []
    for ply in ply_list:
        steamid_list.append(ply.gs_id)

    try:
        info_list = await get_steam_multiple_user_info(app, steamid_list)
    except Exception as e:
        logger.error('Failed to fetch user info.', exc_info=e)
        for ply in ply_list:
            user_list.append(DUserIP(**ply.dict(), gs_name='Unknown Player', gs_avatar=None))
        return user_list

    for ply in ply_list:
        avatar: Optional[DFile] = None
        name: str = 'Unknown Player'

        try:
            info = info_list[ply.gs_id]
            avatar = DFile(**await process_avatar(app, info['avatar_url']))
            name = info['name']
        except Exception as e:
            logger.error('Failed to fetch name or download avatar image.', exc_info=e)

        user_list.append(DUserIP(**ply.dict(), gs_name=name, gs_avatar=avatar))

    return user_list


@gs_router.post(
    '/heartbeat',
    response_model=List[HeartbeatChange],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def heartbeat(
    request: Request, beat: Heartbeat, auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)
):
    if auth[0] != SERVER_KEY:
        raise HTTPException(detail='You must be authed as a server to use this route', status_code=403)

    srv = await DServer.from_id(request.app.state.db[MONGO_DB], auth[1])

    if srv is None:
        raise HTTPException(status_code=500, detail='This should not happen')

    dsi: DServerInfo = DServerInfo.construct()

    dsi.last_updated = datetime.now(tz=UTC).replace(tzinfo=None)

    users = await asyncio.gather(*[_process_heartbeat_player(request.app, ply) for ply in beat.players])

    lup = {}
    i = 0

    for ply in beat.players:
        lup[ply] = users[i]

        # assert ply.gs_service == users[i].gs_service and ply.gs_id == users[i].gs_id

        i += 1

    dsi.players = []

    for user in users:
        dsi.players.append(user)

    dsi.hostname = beat.hostname
    dsi.os = beat.operating_system
    dsi.mod = beat.mod
    dsi.map = beat.map
    dsi.slot_count = beat.max_slots
    dsi.locked = beat.locked

    validate(dsi)

    changes = []

    # Anybody who is present in both the last beat and this new beat should have any time sensitive infractions
    # decremented by the difference between now and then
    if srv.server_info is not None:
        pc = []

        for ply in beat.players:
            if lup[ply] in srv.server_info.players:
                pc.append(ply)

        conds = []

        for p in pc:
            conds.append(
                build_query_dict(
                    auth[0],
                    auth[1],
                    gs_service=p.gs_service,
                    gs_id=p.gs_id,
                    ip=p.ip,
                    ignore_others=not beat.include_other_servers,
                    active_only=True,
                )
            )

        if conds:
            await request.app.state.db[MONGO_DB].infractions.bulk_write(
                [
                    UpdateMany(
                        {
                            '$or': conds,
                            'flags': {'$bitsAllSet': INFRACTION_PLAYTIME_DURATION},
                            'time_left': {'$exists': True, '$ne': 0},
                        },
                        {
                            '$inc': {
                                'time_left': -1 * int((dsi.last_updated - srv.server_info.last_updated).total_seconds())
                            },
                            '$set': {'last_heartbeat': datetime.now(tz=UTC).timestamp()},
                        },
                    ),
                    UpdateMany({'time_left': {'$lt': 0}}, {'$set': {'time_left': 0}}),
                ],
                ordered=True,
            )

            for p in pc:
                changes.append(
                    HeartbeatChange(
                        player=PlayerObjNoIp(**p.dict(by_alias=True)),
                        check=await construct_ci_resp(
                            request.app.state.db[MONGO_DB],
                            build_query_dict(
                                auth[0],
                                auth[1],
                                gs_service=p.gs_service,
                                gs_id=p.gs_id,
                                ip=p.ip,
                                ignore_others=not beat.include_other_servers,
                                active_only=True,
                            ),
                        ),
                    )
                )

    # Save the changes
    srv.server_info = dsi
    await srv.commit(request.app.state.db[MONGO_DB])

    # Log chat messages if provided
    if beat.messages:
        try:
            # Extract unique players from the messages and get their info
            unique_users = {message.user.gs_id: message.user for message in beat.messages if message.user}.values()
            processed_users = await asyncio.gather(
                *[_process_heartbeat_player(request.app, PlayerObjIPOptional(**user.dict())) for user in unique_users]
            )

            # Create a map of gs_id to DUserIP
            user_map = {user.gs_id: processed_user for user, processed_user in zip(unique_users, processed_users)}

            # Prepare chat log documents
            chat_logs = [
                {
                    'user': {
                        **user_map[message.user.gs_id].dict(
                            exclude_unset=True,
                            exclude_none=True,
                            exclude={'gs_avatar'},
                        ),
                        'gs_avatar': {
                            'gridfs_file': user_map[message.user.gs_id].gs_avatar.gridfs_file,
                            'file_name': user_map[message.user.gs_id].gs_avatar.file_name,
                        }
                        if user_map[message.user.gs_id].gs_avatar
                        else None,
                    }
                    if message.user
                    else None,
                    'content': message.content,
                    'created': message.created,
                    'server': ObjectId(auth[1]),
                }
                for message in beat.messages
            ]

            await request.app.state.db[MONGO_DB].chat_logs.insert_many(chat_logs)
        except Exception as e:
            logger.error('Failed to log chat messages.', exc_info=e)

    return changes


@gs_router.get(
    '/vpn', response_model=CheckVPNReply, response_model_exclude_none=True, response_model_exclude_unset=True
)
async def vpn_check(
    request: Request, q: CheckVPN = Depends(CheckVPN), auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)
):
    if auth[0] == NOT_AUTHED_USER:
        raise HTTPException(detail='This route requires authentication', status_code=401)
    cvpn_r = CheckVPNReply(is_vpn=False, is_dubious=False, is_immune=False)

    vpn_result = await check_vpn(request.app, q.player.ip)

    if vpn_result == VPN_YES:
        cvpn_r.is_vpn = True
    elif vpn_result == VPN_DUBIOUS:
        cvpn_r.is_dubious = True

    location = await check_location(request.app, q.player.ip)
    if location:
        cvpn_r.countryName = location

    try:
        if q.player.gs_service is not None and q.player.gs_id is not None:
            adm = await load_admin_from_initiator(
                request.app, Initiator(gs_admin=PlayerObjNoIp(gs_service=q.player.gs_service, gs_id=q.player.gs_id))
            )

            if adm.permissions & PERMISSION_VPN_CHECK_SKIP == PERMISSION_VPN_CHECK_SKIP:
                cvpn_r.is_immune = True
    except NoSuchAdminError:
        pass

    return cvpn_r


@gs_router.post(
    '/calladmin',
    response_model=ExecuteCallAdminReply,
    response_model_exclude_none=True,
    response_model_exclude_unset=True,
)
async def call_admin(
    request: Request, exe: ExecuteCallAdmin, auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)
):
    if auth[0] != SERVER_KEY:
        raise HTTPException(detail='Only servers can use this route', status_code=403)

    srv = await DServer.from_id(request.app.state.db[MONGO_DB], auth[1])

    if srv is None:
        raise HTTPException(status_code=500, detail='This should not happen lol')

    if srv.discord_staff_tag is None or srv.discord_webhook is None:
        raise HTTPException(status_code=405, detail='Call Admin is not configured on this server')

    # Check if the target is banned
    q = build_query_dict(
        auth[0],
        auth[1],
        gs_service=exe.caller.gs_service,
        gs_id=exe.caller.gs_id,
        ignore_others=exe.include_other_servers,
        active_only=True,
    )

    c = await DInfraction.count(
        request.app.state.db[MONGO_DB], {'$and': [q, {'flags': {'$bitsAllSet': INFRACTION_CALL_ADMIN_BAN}}]}
    )

    if c > 0:
        return ExecuteCallAdminReply(sent=False, is_banned=True)

    if srv.last_calladmin + exe.cooldown > datetime.now(tz=UTC).timestamp():
        return ExecuteCallAdminReply(
            sent=False,
            is_banned=False,
            cooldown=((srv.last_calladmin + exe.cooldown) - datetime.now(tz=UTC).timestamp()),
        )

    call_admin_image = await prepare_calladmin_image(exe.image) if exe.image else None

    ct = await execute_webhook(request.app, srv, exe, image=call_admin_image)

    srv.last_calladmin = datetime.now(tz=UTC).timestamp()
    srv.call_data = DCallData(claim_token=ct, call_info=exe)

    asyncio.get_running_loop().create_task(claim_monitor_task(request.app, srv.id, ct))

    await srv.commit(request.app.state.db[MONGO_DB])

    return ExecuteCallAdminReply(sent=True, is_banned=False, cooldown=exe.cooldown)


@gs_router.post(
    '/calladmin/claim',
    response_model=ClaimCallAdminReply,
    response_model_exclude_none=True,
    response_model_exclude_unset=True,
)
async def claim_call(
    request: Request, claim: ClaimCallAdmin, auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)
):
    if auth[0] != SERVER_KEY:
        raise HTTPException(detail='Only servers can use this route', status_code=403)

    srv = await DServer.from_id(request.app.state.db[MONGO_DB], auth[1])

    if srv is None:
        raise HTTPException(status_code=500, detail='This should not happen lol')

    if srv.discord_staff_tag is None or srv.discord_webhook is None:
        raise HTTPException(status_code=405, detail='Call Admin is not configured on this server')

    if srv.call_data is None:
        return ClaimCallAdminReply(success=False, msg='There is no admin call to claim. Was it already claimed?')

    await execute_claim(request.app, srv, claim, srv.call_data)

    srv.call_data = None

    await srv.commit(request.app.state.db[MONGO_DB])

    return ClaimCallAdminReply(success=True)


@gs_router.get('/calladmin/connect')
async def connect(server: str):
    return RedirectResponse(f'steam://connect/{server}')


def init_str(i: Initiator):
    if i.ips_id:
        return str(i.ips_id)
    elif i.mongo_id:
        return str(i.mongo_id)
    elif i.gs_admin:
        return f'{i.gs_admin.gs_service}/{i.gs_admin.gs_id}'


@gs_router.get(
    '/admininfo', response_model=AdminInfo, response_model_exclude_none=True, response_model_exclude_unset=True
)
async def get_admin_info(
    request: Request,
    ips_id: Optional[PositiveInt] = None,
    gs_service: Optional[str] = None,
    gs_id: Optional[str] = None,
    mongo_id: Optional[str] = None,
):
    # Setup objects
    p = None

    if gs_service is not None and gs_id is not None:
        p = PlayerObjNoIp(gs_service=gs_service, gs_id=gs_id)

    init = Initiator(ips_id=ips_id, mongo_id=mongo_id, gs_admin=p)

    with suppress(RedisError):
        ai = await request.app.state.cache.get(f'admin_info:{init_str(init)}', 'get_admin_info_cache')

        if ai is not None:
            return AdminInfo(**ai)

    try:
        adm = await load_admin_from_initiator(request.app, init)
    except NoSuchAdminError:
        raise HTTPException(detail='No Such admin', status_code=404)

    av = None if adm.avatar is None else str(adm.avatar.gridfs_file)

    ai = AdminInfo(admin_name=adm.name, admin_id=adm.ips_id, avatar_id=av, permissions=adm.permissions)

    with suppress(RedisError):
        await request.app.state.cache.set(
            f'admin_info:{init_str(init)}', ai.dict(), 'get_admin_info_cache', expire_time=300
        )

    return ai
