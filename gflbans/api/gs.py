import asyncio
import json
from contextlib import suppress
from datetime import datetime
import re
from typing import Tuple, Optional, List

from redis.exceptions import RedisError
from bson import ObjectId
from dateutil.tz import UTC
from fastapi import APIRouter, Depends, HTTPException
from pydantic import PositiveInt
from pymongo import UpdateMany
from starlette.requests import Request
from fastapi.responses import RedirectResponse
from starlette.background import BackgroundTasks

from gflbans.api.auth import check_access
from gflbans.api_util import str_id, construct_ci_resp, cinfsum_cmp_sef, cinfsum_cmp
from gflbans.internal.asn import check_vpn, VPN_CLOUD, VPN_YES
from gflbans.internal.avatar import process_avatar
from gflbans.internal.config import MONGO_DB
from gflbans.internal.constants import SERVER_KEY, NOT_AUTHED_USER
from gflbans.internal.database.common import DFile, DUser
from gflbans.internal.database.infraction import DComment, build_query_dict, DInfraction
from gflbans.internal.database.server import DServer, DServerInfo, DUserIP, DCallData
from gflbans.internal.database.signature import DSignature
from gflbans.internal.discord_calladmin import claim_monitor_task, execute_webhook, execute_claim, prepare_calladmin_image
from gflbans.internal.errors import NoSuchAdminError
from gflbans.internal.flags import INFRACTION_DEC_ONLINE_ONLY, str2pflag, PERMISSION_VPN_CHECK_SKIP, \
    INFRACTION_CALL_ADMIN_BAN
from gflbans.internal.infraction_utils import create_dinfraction, get_user_data
from gflbans.internal.integrations.games import get_user_info
from gflbans.internal.integrations.games.steam import get_steam_multiple_user_info
from gflbans.internal.log import logger
from gflbans.internal.models.api import PlayerObjNoIp, PlayerObjSimple, Initiator, AdminInfo, PlayerObjIPOptional
from gflbans.internal.models.protocol import HeartbeatChange, Heartbeat, RunSignaturesReply, RunSignatures, \
    CheckVPNReply, \
    CheckVPN, ExecuteCallAdminReply, ExecuteCallAdmin, ClaimCallAdminReply, ClaimCallAdmin
from gflbans.internal.pyapi_utils import load_admin_from_initiator
from gflbans.internal.utils import validate

gs_router = APIRouter()


async def _process_heartbeat_player(app, ply: PlayerObjIPOptional) -> DUserIP:
    avatar: Optional[DFile] = None
    name: str = 'Unknown Player'

    try:
        user_info = await get_user_info(app, ply.gs_service, ply.gs_id)
        avatar = DFile(**await process_avatar(app, user_info['avatar_url']))
        name = user_info['name']
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


@gs_router.post('/heartbeat', response_model=List[HeartbeatChange], response_model_exclude_unset=True,
                response_model_exclude_none=True)
async def heartbeat(request: Request, beat: Heartbeat,
                    auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)):
    if auth[0] != SERVER_KEY: raise HTTPException(detail='You must be authed as a server to use this route',
                                                  status_code=403)

    srv = await DServer.from_id(request.app.state.db[MONGO_DB], auth[1])

    if srv is None:
        raise HTTPException(status_code=500, detail='This should not happen')

    dsi: DServerInfo = DServerInfo.construct()

    dsi.last_updated = datetime.now(tz=UTC).replace(tzinfo=None)

    users = await _process_heartbeat_multiple_players(request.app, beat.players)

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
            conds.append(build_query_dict(auth[0], auth[1], gs_service=p.gs_service, gs_id=p.gs_id,
                                          ip=p.ip, ignore_others=not beat.include_other_servers, active_only=True))

        if conds:
            await request.app.state.db[MONGO_DB].infractions.bulk_write([
                UpdateMany({'$or': conds, 'flags': {'$bitsAllSet': INFRACTION_DEC_ONLINE_ONLY}, 'time_left':
                           {'$exists': True, '$ne': 0}},
                           {'$inc': {'time_left': -1 * int((dsi.last_updated - srv.server_info.last_updated)
                                                           .total_seconds())},
                            '$set': {'last_heartbeat': datetime.now(tz=UTC).timestamp()}}),
                UpdateMany({'time_left': {'$lt': 0}}, {'$set': {'time_left': 0}})
            ], ordered=True)

            for p in pc:
                changes.append(HeartbeatChange(
                    player=PlayerObjNoIp(**p.dict(by_alias=True)),
                    check=await construct_ci_resp(request.app.state.db[MONGO_DB], build_query_dict(auth[0], auth[1], gs_service=p.gs_service,
                                            gs_id=p.gs_id,
                                            ip=p.ip, ignore_others=not beat.include_other_servers, active_only=True))
                ))

    # Save the changes
    srv.server_info = dsi
    await srv.commit(request.app.state.db[MONGO_DB])

    return changes


@gs_router.post('/signatures', response_model=RunSignaturesReply,
                response_model_exclude_unset=True, response_model_exclude_none=True)
async def run_signatures(request: Request,
                         run: RunSignatures, tasks: BackgroundTasks, auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)):
    if auth[0] != SERVER_KEY: raise HTTPException(detail='Must be authed as server for this route', status_code=403)
    vpn_check_result = await check_vpn(request.app, run.player_ip)

    if vpn_check_result == VPN_CLOUD:
        return RunSignaturesReply(num_alts=0, cloud_refused=True)

    num_alts = 0

    q = build_query_dict(auth[0], str_id(auth[1]), gs_service=run.player.gs_service,
                         gs_id=run.player.gs_id,
                         ip=None, ignore_others=(not run.include_other_servers),
                         active_only=True)

    initial_chk = await construct_ci_resp(request.app.state.db[MONGO_DB], q)

    for signature in run.signatures:
        await DSignature.save_signature(request.app.state.db[MONGO_DB], run.player, signature=(signature.mod,
                                                                                             signature.signature))
        
        signature = signature.to_signature()
        logger.debug(f'check signature {signature.mod} {signature.signature}')
        
        async for dsig in DSignature.find_all_of_signature(request.app.state.db[MONGO_DB],
                                                           signature=(signature.mod, signature.signature)):
            if dsig.user.gs_service != run.player.gs_service or dsig.user.gs_id != run.player.gs_id:
                num_alts += 1

                q2 = build_query_dict(auth[0], str_id(auth[1]), gs_service=dsig.user.gs_service,
                                      gs_id=dsig.user.gs_id,
                                      ip=None, ignore_others=(not run.include_other_servers),
                                      active_only=True)

                chk = await construct_ci_resp(request.app.state.db[MONGO_DB], q2)

                # If ANY field exceeds, add an evasion punishment

                if cinfsum_cmp_sef(initial_chk.voice_block, chk.voice_block) or \
                        cinfsum_cmp_sef(initial_chk.chat_block, chk.chat_block) or \
                        cinfsum_cmp_sef(initial_chk.ban, chk.ban) or \
                        cinfsum_cmp_sef(initial_chk.admin_chat_block, chk.admin_chat_block) or \
                        cinfsum_cmp_sef(initial_chk.call_admin_block, chk.call_admin_block):
                    v = []

                    for fn in str2pflag.keys():
                        if hasattr(chk, fn) and getattr(chk, fn) is not None:
                            v.append(fn)

                    def pick_worst(c):
                        w = None
                        for fn2 in str2pflag.keys():
                            if hasattr(c, fn2) and getattr(c, fn2) is not None:
                                if w is None:
                                    w = getattr(c, fn2)
                                else:
                                    w = cinfsum_cmp(w, getattr(c, fn2))

                        if w.expiration is None:
                            return None
                        else:
                            a = w.expiration - int(datetime.now(tz=UTC).timestamp())

                            if a > 0:
                                return a
                            else:
                                return 60

                    s = 'global' if run.include_other_servers else 'server'
                    d = None if run.make_permanent_for_evasion else pick_worst(chk)

                    dinf = create_dinfraction(PlayerObjSimple(
                        gs_service=run.player.gs_service,
                        gs_id=run.player.gs_id,
                        ip=run.player_ip
                    ), reason=f'Punishment evasion: {dsig.user.gs_service} {dsig.user.gs_id}', scope=s,
                        punishments=v, duration=d, server=auth[1])
                    
                    dc = DComment(content=f'ref: {dsig.mod}/{dsig.signature}', private=True, created=datetime.now(tz=UTC))

                    dinf.comments.append(dc)

                    await dinf.commit(request.app.state.db[MONGO_DB])

                    tasks.add_task(get_user_data, request.app, dinf.id, True)

    return RunSignaturesReply(check=await construct_ci_resp(request.app.state.db[MONGO_DB], q), num_alts=num_alts)


@gs_router.get('/alts', response_model=List[PlayerObjNoIp], response_model_exclude_none=True,
               response_model_exclude_unset=True)
async def get_alts(request: Request, ply: PlayerObjNoIp = Depends(PlayerObjNoIp),
                   auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)):
    if auth == NOT_AUTHED_USER: raise HTTPException(detail='This route requires authentication', status_code=401)

    alts = []

    async for signature in DSignature.find_all_signatures_of_users(request.app.state.db[MONGO_DB], ply.gs_service,
                                                                   ply.gs_id):
        async for alt_sig in DSignature.find_all_of_signature(request.app.state.db[MONGO_DB],
                                                              (signature.mod, signature.signature)):
            if alt_sig.user != ply and alt_sig.user not in alts:
                alts.append(alt_sig.user)

    return alts


@gs_router.get('/vpn', response_model=CheckVPNReply,
               response_model_exclude_none=True, response_model_exclude_unset=True)
async def vpn_check(request: Request, q: CheckVPN = Depends(CheckVPN),
                    auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)):
    if auth[0] == NOT_AUTHED_USER: raise HTTPException(detail='This route requires authentication', status_code=401)
    cvpn_r = CheckVPNReply(is_vpn=False, is_cloud_gaming=False, is_immune=False)

    vpn_result = await check_vpn(request.app, q.player.ip)

    if vpn_result == VPN_YES:
        cvpn_r.is_vpn = True
    elif vpn_result == VPN_CLOUD:
        cvpn_r.is_cloud_gaming = True

    try:
        if q.player.gs_service is not None and q.player.gs_id is not None:
            adm = await load_admin_from_initiator(request.app,
                                                Initiator(gs_admin=PlayerObjNoIp(gs_service=q.player.gs_service,
                                                                                gs_id=q.player.gs_id)))

            if adm.permissions & PERMISSION_VPN_CHECK_SKIP == PERMISSION_VPN_CHECK_SKIP:
                cvpn_r.is_immune = True
    except NoSuchAdminError:
        pass

    return cvpn_r


@gs_router.post('/calladmin', response_model=ExecuteCallAdminReply,
                response_model_exclude_none=True, response_model_exclude_unset=True)
async def call_admin(request: Request, exe: ExecuteCallAdmin,
                     auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)):
    if auth[0] != SERVER_KEY: raise HTTPException(detail='Only servers can use this route', status_code=403)

    srv = await DServer.from_id(request.app.state.db[MONGO_DB], auth[1])

    if srv is None:
        raise HTTPException(status_code=500, detail='This should not happen lol')

    if srv.discord_staff_tag is None or srv.discord_webhook is None:
        raise HTTPException(status_code=405, detail='Call Admin is not configured on this server')

    # Check if the target is banned
    q = build_query_dict(auth[0], auth[1], gs_service=exe.caller.gs_service, gs_id=exe.caller.gs_id,
                         ignore_others=exe.include_other_servers, active_only=True)

    c = await DInfraction.count(request.app.state.db[MONGO_DB], {'$and': [
        q,
        {'flags': {'$bitsAllSet': INFRACTION_CALL_ADMIN_BAN}}
    ]})

    if c > 0:
        return ExecuteCallAdminReply(sent=False, is_banned=True)

    if srv.last_calladmin + exe.cooldown > datetime.now(tz=UTC).timestamp():
        return ExecuteCallAdminReply(sent=False, is_banned=False, cooldown=((srv.last_calladmin + exe.cooldown) -datetime.now(
            tz=UTC).timestamp()))

    call_admin_image = await prepare_calladmin_image(exe.image) if exe.image else None

    ct = await execute_webhook(request.app, srv, exe, image=call_admin_image)

    srv.last_calladmin = datetime.now(tz=UTC).timestamp()
    srv.call_data = DCallData(claim_token=ct, call_info=exe)

    asyncio.get_running_loop().create_task(claim_monitor_task(request.app, srv.id, ct))

    await srv.commit(request.app.state.db[MONGO_DB])

    return ExecuteCallAdminReply(sent=True, is_banned=False, cooldown=exe.cooldown)


@gs_router.post('/calladmin/claim', response_model=ClaimCallAdminReply,
                response_model_exclude_none=True, response_model_exclude_unset=True)
async def claim_call(request: Request, claim: ClaimCallAdmin,
                     auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)):
    if auth[0] != SERVER_KEY: raise HTTPException(detail='Only servers can use this route', status_code=403)

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


@gs_router.get('/admininfo', response_model=AdminInfo, response_model_exclude_none=True,
               response_model_exclude_unset=True)
async def get_admin_info(request: Request, ips_id: Optional[PositiveInt] = None, gs_service: Optional[str] = None, gs_id: Optional[str] = None, mongo_id: Optional[str] = None):
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
        await request.app.state.cache.set(f'admin_info:{init_str(init)}', ai.dict(), 'get_admin_info_cache',
                                          expire_time=300)

    return ai
