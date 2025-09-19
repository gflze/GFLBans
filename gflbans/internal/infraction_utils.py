import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Union

from aiohttp import ClientResponseError
from bson import ObjectId
from dateutil.tz import UTC
from fastapi import HTTPException
from humanize import naturaldelta
from pydantic import PositiveInt

# This function does no permission checks. It merely constructs a DInfraction object without saving it
# with the desired parameters
from gflbans.api_util import construct_ci_resp
from gflbans.internal.asn import VPN_DUBIOUS, VPN_YES, check_vpn
from gflbans.internal.avatar import process_avatar
from gflbans.internal.config import BRANDING, COMMUNITY_ICON, GFLBANS_ICON, GLOBAL_INFRACTION_WEBHOOK, HOST, MONGO_DB
from gflbans.internal.constants import GB_VERSION, SERVER_KEY
from gflbans.internal.database.admin import Admin
from gflbans.internal.database.common import DFile
from gflbans.internal.database.infraction import DInfraction, DUser, build_query_dict
from gflbans.internal.database.rpc import DRPCPlayerUpdated
from gflbans.internal.database.server import DServer
from gflbans.internal.database.task import DTask
from gflbans.internal.discord_calladmin import sanitize_discord_username
from gflbans.internal.errors import NoSuchAdminError
from gflbans.internal.flags import (
    INFRACTION_ADMIN_CHAT_BLOCK,
    INFRACTION_BAN,
    INFRACTION_CALL_ADMIN_BAN,
    INFRACTION_CHAT_BLOCK,
    INFRACTION_GLOBAL,
    INFRACTION_ITEM_BLOCK,
    INFRACTION_PERMANENT,
    INFRACTION_PLAYTIME_DURATION,
    INFRACTION_REMOVED,
    INFRACTION_SESSION,
    INFRACTION_SYSTEM,
    INFRACTION_VOICE_BLOCK,
    INFRACTION_VPN,
    INFRACTION_WEB,
    PERMISSION_CREATE_INFRACTION,
    PERMISSION_IMMUNE,
    PERMISSION_SCOPE_GLOBAL,
    PERMISSION_SKIP_IMMUNITY,
    scope_to_flag,
    str2permflag,
    str2pflag,
)
from gflbans.internal.integrations.games import get_user_info, validate_id_ex
from gflbans.internal.integrations.ips import ips_get_gsid_from_member_id
from gflbans.internal.log import logger
from gflbans.internal.models.api import Initiator, PlayerObjNoIp, PlayerObjSimple, PositiveIntIncl0
from gflbans.internal.pyapi_utils import load_admin_from_initiator


def filter_badchars(s):
    return s.replace('\n', ' ')


def create_dinfraction(
    player: PlayerObjSimple,
    reason: str,
    scope: str,
    punishments: List,
    session: bool = False,
    created: int = None,
    duration: int = None,
    admin: ObjectId = None,
    playtime_based: bool = False,
    server: ObjectId = None,
) -> DInfraction:
    dinf = DInfraction.construct()

    if player.gs_service is not None:
        validate_id_ex(PlayerObjNoIp(gs_service=player.gs_service, gs_id=player.gs_id))
        dinf.user = DUser(gs_service=player.gs_service, gs_id=player.gs_id)
    dinf.ip = player.ip
    dinf.reason = filter_badchars(reason)

    # scope
    s = scope.lower()
    dinf.flags |= scope_to_flag[s]

    # punishments
    for punishment in punishments:
        dinf.flags |= str2pflag[punishment]

    # expiration related business
    if session:
        dinf.flags |= INFRACTION_SESSION
    elif duration is None:
        dinf.flags |= INFRACTION_PERMANENT
    elif playtime_based:
        dinf.original_time = duration
        dinf.time_left = duration
        dinf.flags |= INFRACTION_PLAYTIME_DURATION
    else:
        dinf.expires = datetime.now(tz=UTC).timestamp() + duration

    # creation timestamp
    if created:
        dinf.created = created
    else:
        dinf.created = datetime.now(tz=UTC).timestamp()

    # server or web
    if server:
        dinf.server = server
    else:
        dinf.flags |= INFRACTION_WEB

    if admin:
        dinf.admin = admin
    else:
        dinf.flags |= INFRACTION_SYSTEM

    return dinf


async def get_user_data(
    app, infraction_id: ObjectId, reschedule_on_fail=False, print_map_in_discord_embed: bool = False
):
    try:
        dinf = await DInfraction.from_id(app.state.db[MONGO_DB], infraction_id)

        if dinf is None:
            logger.warning(f'Tried to get_user_data for {str(infraction_id)}, but no such document exists.')
            return

        assert dinf.user is not None

        user_info = await get_user_info(app, dinf.user.gs_service, dinf.user.gs_id)

        duser = dinf.user
        duser.gs_name = user_info['name']
        try:
            duser.gs_avatar = DFile(**await process_avatar(app, user_info['avatar_url']))
        except Exception as e:
            """ If avatar failed but everything else was fine, just dont store an avatar in the
                infraction but store name still. This should hopefully only happen in rare cases
                where Steam deletes the picture on the backend but for some reason leaves the
                deleted URL as the person's steam avatar. """
            logger.warning('get_user_data failed to find an avatar. Leaving as empty in the infraction.', exc_info=e)
            pass

        await dinf.update_field(app.state.db[MONGO_DB], 'user', duser)

        await discord_notify_create_infraction(app, dinf, print_map_in_discord_embed)
    except Exception as e:
        logger.error('get_user_data failed!', exc_info=e)
        if reschedule_on_fail:
            logger.info(f'Rescheduling get_user_data call for {str(infraction_id)})...')
            dt = DTask(
                run_at=datetime.now(tz=UTC).timestamp() + 5,
                task_data={'i_id': infraction_id},
                ev_handler='get_user_data',
            )
            await dt.commit(app.state.db[MONGO_DB])
        raise


async def get_vpn_data(app, infraction_id: ObjectId, reschedule_on_fail=False):
    try:
        dinf = await DInfraction.from_id(app.state.db[MONGO_DB], infraction_id)

        if dinf is None:
            logger.warning(f'Tried to get_vpn_data for {str(infraction_id)}, but no such document exists.')
            return

        assert dinf.ip is not None

        vpn_state = await check_vpn(app, dinf.ip)

        if vpn_state == VPN_YES or vpn_state == VPN_DUBIOUS:
            logger.info(f'{dinf.ip} is a vpn or suspicious IP address.')

            await dinf.add_bit_flag(app.state.db[MONGO_DB], 'flags', INFRACTION_VPN)
    except Exception as e:
        logger.error('get_vpn_data failed!', exc_info=e)
        if reschedule_on_fail:
            logger.info(f'Rescheduling get_vpn_data call for {str(infraction_id)})...')
            dt = DTask(
                run_at=datetime.now(tz=UTC).timestamp() + 5,
                task_data={'i_id': infraction_id},
                ev_handler='get_vpn_data',
            )
            await dt.commit(app.state.db[MONGO_DB])
        raise


def target_name(dinf: DInfraction) -> str:
    if dinf.user is not None:
        if dinf.user.gs_name is not None:
            return dinf.user.gs_name
        else:
            return f'{dinf.user.gs_service}/{dinf.user.gs_id}'
    elif dinf.ip is not None:
        return 'an IP Address'
    else:
        return 'Unknown Player'


async def _embed_host(db_ref, dsrv_ref: Optional[ObjectId]):
    if dsrv_ref is None:
        return 'GFLBans Web'

    srv = await DServer.from_id(db_ref, dsrv_ref)

    if srv is None:
        return 'GFLBans Web'
    elif srv.server_info is not None:
        return srv.server_info.hostname
    elif srv.friendly_name is not None:
        return srv.friendly_name
    else:
        return f'{srv.ip}:{srv.game_port}'


async def modify_infraction(
    app,
    target: ObjectId,
    author: Union[ObjectId, str, None] = None,
    make_session: bool = False,
    make_permanent: bool = False,
    expiration: Optional[PositiveInt] = None,
    time_left: Optional[PositiveIntIncl0] = None,
    server: Optional[ObjectId] = None,
    reason: Optional[str] = None,
    set_removal_state: Optional[bool] = None,
    removed_by: Optional[ObjectId] = None,
    removal_reason: Optional[str] = None,
    punishments: Optional[List] = None,
    scope: Optional[str] = None,
    vpn: Optional[bool] = None,
    make_web: bool = False,
    reuse_dinf: DInfraction = None,
    actor: Optional[ObjectId] = None,
):
    if reuse_dinf is not None and reuse_dinf.id == target:
        dinf = reuse_dinf
    else:
        dinf = await DInfraction.from_id(app.state.db[MONGO_DB], target)

    if dinf is None:
        raise TypeError('Expected DInfraction, got none')  # catch and replace

    db = app.state.db[MONGO_DB]

    commit_list = []
    changes = {}
    removed = None

    def uwu(var, old, new):
        changes[var] = {'old': old, 'new': new}

    # async with await app.state.db.start_session() as session:
    # async with session.start_transaction():

    # Handle an owner update
    if author is not None:
        if isinstance(author, str):
            # SYSTEM

            if dinf.flags & INFRACTION_SYSTEM != INFRACTION_SYSTEM and dinf.admin is not None:
                uwu('Owner', await load_admin_from_initiator(app, Initiator(mongo_id=str(dinf.admin))).name, 'System')

            commit_list.append(dinf.unset_field(db, 'admin'))
            commit_list.append(dinf.add_bit_flag(db, 'flags', INFRACTION_SYSTEM))
        elif isinstance(author, ObjectId):
            if dinf.flags & INFRACTION_SYSTEM == INFRACTION_SYSTEM:
                uwu('Owner', 'System', await load_admin_from_initiator(app, Initiator(mongo_id=str(author))).name)
            else:
                uwu(
                    'Owner',
                    await load_admin_from_initiator(
                        app, Initiator(mongo_id=str(dinf.admin) if dinf.admin is not None else None)
                    ).name,
                    await load_admin_from_initiator(app, Initiator(mongo_id=str(author))).name,
                )

            commit_list.append(dinf.update_field(db, 'admin', author))
            commit_list.append(dinf.remove_bit_flag(db, 'flags', INFRACTION_SYSTEM))
        else:
            raise ValueError('Attempted to do an author update with an unsupported author type')

    # Handle changing of the expiration properties of the infraction
    fl = ['expires', 'time_left', 'original_time']
    fl2 = [INFRACTION_SESSION, INFRACTION_PERMANENT, INFRACTION_PLAYTIME_DURATION]

    def clear_expiration_stuff():
        for field in fl:
            commit_list.append(dinf.unset_field(db, field))
        v = 0
        for flag in fl2:
            v |= flag
        if v != 0:
            commit_list.append(dinf.remove_bit_flag(db, 'flags', v))

    def exp_orig_value():
        if dinf.flags & INFRACTION_PERMANENT == INFRACTION_PERMANENT:
            return 'Permanent'
        elif dinf.flags & INFRACTION_SESSION == INFRACTION_SESSION:
            return 'Session'
        elif dinf.flags & INFRACTION_PLAYTIME_DURATION == INFRACTION_PLAYTIME_DURATION:
            return naturaldelta(timedelta(seconds=dinf.original_time))
        elif dinf.expires is None:
            return 'ERROR'
        else:
            return naturaldelta(timedelta(seconds=(dinf.expires - dinf.created)))

    if make_session:
        uwu('Duration', exp_orig_value(), 'Session')
        clear_expiration_stuff()
        commit_list.append(dinf.add_bit_flag(db, 'flags', INFRACTION_SESSION))
    elif make_permanent:
        uwu('Duration', exp_orig_value(), 'Permanent')
        clear_expiration_stuff()
        commit_list.append(dinf.add_bit_flag(db, 'flags', INFRACTION_PERMANENT))
    elif expiration is not None:
        uwu('Duration', exp_orig_value(), naturaldelta(timedelta(seconds=(expiration))))
        clear_expiration_stuff()
        commit_list.append(dinf.update_field(db, 'expires', expiration + dinf.created))
    elif time_left is not None:
        if dinf.flags & INFRACTION_BAN == INFRACTION_BAN and (punishments is None or 'ban' in punishments):
            raise ValueError('Cannot make a ban based on playtime')

        uwu('Duration', exp_orig_value(), naturaldelta(timedelta(seconds=time_left)))
        clear_expiration_stuff()
        if dinf.time_left is not None and dinf.original_time is not None:
            actual_time_left = time_left - (dinf.original_time - dinf.time_left)
            if actual_time_left < 0:
                actual_time_left = 0
            commit_list.append(dinf.update_field(db, 'time_left', actual_time_left))
            commit_list.append(dinf.update_field(db, 'original_time', time_left))
        else:
            commit_list.append(dinf.update_field(db, 'time_left', time_left))
            commit_list.append(dinf.update_field(db, 'original_time', time_left))
        commit_list.append(dinf.add_bit_flag(db, 'flags', INFRACTION_PLAYTIME_DURATION))

    if make_web:
        uwu('Server', await _embed_host(app.state.db[MONGO_DB], dinf.server), 'GFLBans Web')
        commit_list.append(dinf.unset_field(db, 'server'))
        commit_list.append(dinf.add_bit_flag(db, 'flags', INFRACTION_WEB))
    elif server is not None:
        uwu(
            'Server',
            await _embed_host(app.state.db[MONGO_DB], dinf.server),
            await _embed_host(app.state.db[MONGO_DB], server),
        )
        commit_list.append(dinf.remove_bit_flag(db, 'flags', INFRACTION_WEB))
        commit_list.append(dinf.update_field(db, 'server', server))

    if reason is not None:
        uwu('Reason', dinf.reason, reason)
        commit_list.append(dinf.update_field(db, 'reason', filter_badchars(reason)))

    if set_removal_state is not None:
        if set_removal_state:
            if dinf.flags & INFRACTION_REMOVED == INFRACTION_REMOVED:
                raise ValueError('Tried to remove an infraction that was already removed.')

            removed = True

            commit_list.append(dinf.add_bit_flag(db, 'flags', INFRACTION_REMOVED))
            commit_list.append(dinf.update_field(db, 'ureason', filter_badchars(removal_reason)))
            commit_list.append(dinf.update_field(db, 'removed', int(datetime.now(tz=UTC).timestamp())))
            commit_list.append(dinf.update_field(db, 'remover', removed_by))
        else:
            if dinf.flags & INFRACTION_REMOVED != INFRACTION_REMOVED:
                raise ValueError('Tried to re-instate infraction that was not removed.')

            removed = False

            commit_list.append(dinf.remove_bit_flag(db, 'flags', INFRACTION_REMOVED))
            commit_list.append(dinf.unset_field(db, 'ureason'))
            commit_list.append(dinf.unset_field(db, 'removed'))
            commit_list.append(dinf.unset_field(db, 'remover'))

    def _lang(a):
        if a == 'voice_block':
            return 'Voice Block'
        elif a == 'chat_block':
            return 'Text Block'
        elif a == 'ban':
            return 'Ban'
        elif a == 'admin_chat_block':
            return 'Admin Chat Block'
        elif a == 'call_admin_block':
            return 'Call Admin Block'
        elif a == 'item_block':
            return 'Item Block'
        else:
            return '[OMG YOU FORGOT TO UPDATE THIS]'

    def _uwu2(a):
        if not a:
            return 'Warning'

        return ', '.join([_lang(b) for b in a])

    if punishments is not None:
        if 'ban' in punishments and dinf.flags & INFRACTION_PLAYTIME_DURATION == INFRACTION_PLAYTIME_DURATION:
            raise ValueError('Cannot make a playtime based infraction into a ban')
        t = 0
        old_res = []
        for k, val in str2pflag.items():
            t |= val

            if dinf.flags & val == val:
                old_res.append(k)

        commit_list.append(dinf.remove_bit_flag(db, 'flags', t))

        t = 0

        for p in punishments:
            t |= str2pflag[p]

        commit_list.append(dinf.add_bit_flag(db, 'flags', t))

        uwu('Restrictions', _uwu2(old_res), _uwu2(punishments))

    if scope is not None:
        if dinf.flags & INFRACTION_GLOBAL == INFRACTION_GLOBAL:
            uwu('Scope', 'Global', scope)
        else:
            uwu('Scope', 'Server Only', scope)

        commit_list.append(dinf.remove_bit_flag(db, 'flags', INFRACTION_GLOBAL))

        commit_list.append(dinf.add_bit_flag(db, 'flags', scope_to_flag[scope]))

    if vpn is not None:
        if vpn:
            uwu('Is VPN?', 'No', 'Yes')
            commit_list.append(dinf.add_bit_flag(db, 'flags', INFRACTION_VPN))
        else:
            uwu('Is VPN?', 'Yes', 'No')
            commit_list.append(dinf.remove_bit_flag(db, 'flags', INFRACTION_VPN))

    for coro in commit_list:
        await coro

    if removed is None:
        await discord_notify_edit_infraction(app, dinf, actor, changes)
    elif removed:
        await discord_notify_revoke_infraction(app, dinf, actor)
    else:
        await discord_notify_reinst_infraction(app, dinf, actor)


async def push_state_to_nodes(app, dinf: DInfraction):
    gathers = []

    logger.debug('enter push_state_to_nodes')

    async def load_user(s, user):
        logger.debug('enter load_user')

        local = build_query_dict(
            SERVER_KEY, str(s.id), gs_service=user.gs_service, gs_id=user.gs_id, ignore_others=True, active_only=True
        )

        glob = build_query_dict(
            SERVER_KEY, str(s.id), gs_service=user.gs_service, gs_id=user.gs_id, ignore_others=False, active_only=True
        )

        ci_resp_local = await construct_ci_resp(app.state.db[MONGO_DB], local)
        ci_resp_global = await construct_ci_resp(app.state.db[MONGO_DB], glob)

        r = DRPCPlayerUpdated(
            target_type='player',
            target_payload=PlayerObjNoIp(gs_service=user.gs_service, gs_id=user.gs_id),
            local=ci_resp_local,
            glob=ci_resp_global,
            time=datetime.now(tz=UTC),
            target=s.id,
        )

        await r.commit(app.state.db[MONGO_DB])

    async def load_ip(s, ip):
        logger.debug('enter load_ip')

        local = build_query_dict(SERVER_KEY, str(s.id), ip=ip, ignore_others=True, active_only=True)

        glob = build_query_dict(SERVER_KEY, str(s.id), ip=ip, ignore_others=False, active_only=True)

        ci_resp_local = await construct_ci_resp(app.state.db[MONGO_DB], local)
        ci_resp_global = await construct_ci_resp(app.state.db[MONGO_DB], glob)

        r = DRPCPlayerUpdated(
            target_type='ip',
            target_payload=ip,
            local=ci_resp_local,
            glob=ci_resp_global,
            time=datetime.now(tz=UTC),
            target=s.id,
        )

        await r.commit(app.state.db[MONGO_DB])

    async for srv in DServer.from_query_ex(app.state.db[MONGO_DB], {}):
        if dinf.user is not None:
            gathers.append(load_user(srv, dinf.user))

        if dinf.ip:
            gathers.append(load_ip(srv, dinf.ip))

    await asyncio.gather(*gathers)


_nouns = {
    INFRACTION_VOICE_BLOCK: 'Mute',
    INFRACTION_CHAT_BLOCK: 'Gag',
    INFRACTION_BAN: 'Ban',
    INFRACTION_ADMIN_CHAT_BLOCK: 'Admin Chat Gag',
    INFRACTION_CALL_ADMIN_BAN: 'Call Admin Ban',
    INFRACTION_VOICE_BLOCK | INFRACTION_CHAT_BLOCK: 'Silence',
    INFRACTION_ITEM_BLOCK: 'Item Restriction',
}


def punishment_noun(dinf: DInfraction) -> str:
    for k, v in _nouns.items():
        others = (
            INFRACTION_VOICE_BLOCK
            | INFRACTION_CHAT_BLOCK
            | INFRACTION_BAN
            | INFRACTION_ADMIN_CHAT_BLOCK
            | INFRACTION_CALL_ADMIN_BAN
            | INFRACTION_ITEM_BLOCK
        ) & ~k

        if dinf.flags & k == k and dinf.flags & others == 0:
            return v

        if (
            dinf.flags
            & (
                INFRACTION_VOICE_BLOCK
                | INFRACTION_CHAT_BLOCK
                | INFRACTION_BAN
                | INFRACTION_ADMIN_CHAT_BLOCK
                | INFRACTION_CALL_ADMIN_BAN
                | INFRACTION_ITEM_BLOCK
            )
            == 0
        ):
            return 'Warning'

    return 'Infraction'


def get_permissions(dinf: DInfraction) -> int:
    i = PERMISSION_CREATE_INFRACTION

    for pun_str, pun_flag in str2pflag.items():
        if dinf.flags & pun_flag == pun_flag:
            i |= str2permflag[pun_str]

    if dinf.flags & INFRACTION_GLOBAL == INFRACTION_GLOBAL:
        i |= PERMISSION_SCOPE_GLOBAL

    return i


async def embed_author(app, admin_id: Optional[ObjectId]):
    if admin_id is not None:
        adm = await load_admin_from_initiator(app, Initiator(mongo_id=str(admin_id)))

        await adm.fetch_details(app)

        return {
            'name': adm.name,
            'icon_url': f'http://{HOST}/static/images/fallback_av.png'
            if adm.avatar is None
            else f'http://{HOST}/file/uploads/{adm.avatar.gridfs_file}/avatar.webp',
            'url': f'https://steamcommunity.com/profiles/{ips_get_gsid_from_member_id(adm.ips_id)}/',
        }
    else:
        return {'name': 'System', 'icon_url': f'http://{HOST}/static/images/fallback_av.png'}


def target_avatar(dinf: DInfraction):
    if dinf.user and dinf.user.gs_avatar:
        return f'http://{HOST}/file/uploads/{dinf.user.gs_avatar.gridfs_file}/avatar.webp'
    else:
        return f'http://{HOST}/static/images/fallback_av.png'


def target_link(dinf: DInfraction):
    if dinf.user is None:
        return 'IP Address'

    name = 'Unknown Player' if dinf.user.gs_name is None else dinf.user.gs_name

    if dinf.user.gs_service == 'steam':
        return f'[{sanitize_discord_username(name)}](https://steamcommunity.com/profiles/{dinf.user.gs_id})'
    else:
        return name


def embed_duration(dinf: DInfraction):
    if dinf.original_time is not None:
        return naturaldelta(timedelta(seconds=dinf.original_time)).capitalize()
    elif dinf.expires is not None:
        return naturaldelta(timedelta(seconds=dinf.expires - dinf.created)).capitalize()
    elif dinf.flags & INFRACTION_PERMANENT == INFRACTION_PERMANENT:
        return 'Permanent'
    elif dinf.flags & INFRACTION_SESSION == INFRACTION_SESSION:
        return 'Session'
    else:
        return 'OOPS, INVALID!'


async def discord_notify_create_infraction(app, dinf: DInfraction, print_map: bool = False):
    bot_name = f'{BRANDING}'
    bot_avatar = COMMUNITY_ICON

    embed = {
        'username': bot_name,
        'avatar_url': bot_avatar,
        'embeds': [
            {
                'title': f'New {punishment_noun(dinf)} on {target_name(dinf)}',
                'color': 9371903,
                'author': await embed_author(app, dinf.admin),
                'url': f'http://{HOST}/infractions/{str(dinf.id)}/',
                'thumbnail': {'url': target_avatar(dinf)},
                'footer': {'icon_url': GFLBANS_ICON, 'text': await _embed_host(app.state.db[MONGO_DB], dinf.server)},
                'timestamp': datetime.fromtimestamp(dinf.created, tz=UTC).strftime('%Y-%m-%dT%H:%M:%SZ'),
                'fields': [
                    {'name': 'Player', 'value': target_link(dinf), 'inline': True},
                    {'name': 'Duration', 'value': embed_duration(dinf), 'inline': True},
                    {'name': 'Reason', 'value': dinf.reason},
                ],
            }
        ],
    }

    if dinf.server is not None:
        srv = await DServer.from_id(app.state.db[MONGO_DB], dinf.server)
    else:
        srv = None

    if print_map and srv is not None:
        embed['embeds'][0]['fields'].append(
            {
                'name': 'Map',
                'value': srv.server_info.map,
            },
        )

    if srv is not None and srv.infract_webhook is not None:
        async with app.state.aio_session.post(
            srv.infract_webhook + '?wait=true', headers={'User-Agent': f'{BRANDING} ({HOST}, {GB_VERSION})'}, json=embed
        ) as resp:
            try:
                resp.raise_for_status()
            except Exception:
                logger.error('Failed to post infraction to srv infract webhook', exc_info=True)

    if GLOBAL_INFRACTION_WEBHOOK is not None:
        async with app.state.aio_session.post(
            GLOBAL_INFRACTION_WEBHOOK + '?wait=true',
            headers={'User-Agent': f'{BRANDING} ({HOST}, {GB_VERSION})'},
            json=embed,
        ) as resp:
            try:
                resp.raise_for_status()
            except Exception:
                logger.error('Failed to post infraction to global infract webhook', exc_info=True)


async def discord_notify_edit_infraction(app, dinf: DInfraction, editor: Optional[ObjectId], changes):
    bot_name = f'{BRANDING}'
    bot_avatar = COMMUNITY_ICON

    embed = {
        'username': bot_name,
        'avatar_url': bot_avatar,
        'embeds': [
            {
                'title': f'{punishment_noun(dinf)} on {target_name(dinf)} Updated',
                'color': 1104124,
                'author': await embed_author(app, editor),
                'url': f'http://{HOST}/infractions/{str(dinf.id)}/',
                'thumbnail': {'url': target_avatar(dinf)},
                'footer': {'icon_url': GFLBANS_ICON, 'text': await _embed_host(app.state.db[MONGO_DB], dinf.server)},
                'timestamp': datetime.fromtimestamp(dinf.created, tz=UTC).strftime('%Y-%m-%dT%H:%M:%SZ'),
                'fields': [],
            }
        ],
    }

    for k, v in changes.items():
        embed['embeds'][0]['fields'].append({'name': k, 'value': f'~~{v["old"]}~~ → {v["new"]}'})

    if dinf.server is not None:
        srv = await DServer.from_id(app.state.db[MONGO_DB], dinf.server)
    else:
        srv = None

    if srv is not None and srv.infract_webhook is not None:
        async with app.state.aio_session.post(
            srv.infract_webhook + '?wait=true', headers={'User-Agent': f'{BRANDING} ({HOST}, {GB_VERSION})'}, json=embed
        ) as resp:
            try:
                resp.raise_for_status()
            except Exception:
                logger.error('Failed to post infraction to srv infract webhook', exc_info=True)

    if GLOBAL_INFRACTION_WEBHOOK is not None:
        async with app.state.aio_session.post(
            GLOBAL_INFRACTION_WEBHOOK + '?wait=true',
            headers={'User-Agent': f'{BRANDING} ({HOST}, {GB_VERSION})'},
            json=embed,
        ) as resp:
            try:
                resp.raise_for_status()
            except Exception:
                logger.error('Failed to post infraction to global infract webhook', exc_info=True)


async def discord_notify_revoke_infraction(app, dinf: DInfraction, actor: Optional[ObjectId]):
    bot_name = f'{BRANDING}'
    bot_avatar = COMMUNITY_ICON

    embed = {
        'username': bot_name,
        'avatar_url': bot_avatar,
        'embeds': [
            {
                'title': f'Revoked {punishment_noun(dinf)} on {target_name(dinf)}',
                'color': 16711792,
                'author': await embed_author(app, actor),
                'url': f'http://{HOST}/infractions/{str(dinf.id)}/',
                'thumbnail': {'url': target_avatar(dinf)},
                'footer': {'icon_url': GFLBANS_ICON, 'text': await _embed_host(app.state.db[MONGO_DB], dinf.server)},
                'timestamp': datetime.fromtimestamp(dinf.removed, tz=UTC).strftime('%Y-%m-%dT%H:%M:%SZ'),
                'fields': [
                    {'name': 'Player', 'value': target_link(dinf), 'inline': True},
                    {'name': 'Duration', 'value': embed_duration(dinf), 'inline': True},
                    {'name': 'Reason', 'value': dinf.reason},
                    {'name': 'Removal Reason', 'value': dinf.ureason},
                ],
            }
        ],
    }

    if dinf.server is not None:
        srv = await DServer.from_id(app.state.db[MONGO_DB], dinf.server)
    else:
        srv = None

    if srv is not None and srv.infract_webhook is not None:
        async with app.state.aio_session.post(
            srv.infract_webhook + '?wait=true', headers={'User-Agent': f'{BRANDING} ({HOST}, {GB_VERSION})'}, json=embed
        ) as resp:
            try:
                resp.raise_for_status()
            except Exception:
                logger.error('Failed to post infraction to srv infract webhook', exc_info=True)

    if GLOBAL_INFRACTION_WEBHOOK is not None:
        async with app.state.aio_session.post(
            GLOBAL_INFRACTION_WEBHOOK + '?wait=true',
            headers={'User-Agent': f'{BRANDING} ({HOST}, {GB_VERSION})'},
            json=embed,
        ) as resp:
            try:
                resp.raise_for_status()
            except Exception:
                logger.error('Failed to post infraction to global infract webhook', exc_info=True)


async def discord_notify_reinst_infraction(app, dinf: DInfraction, actor: Optional[ObjectId]):
    bot_name = f'{BRANDING}'
    bot_avatar = COMMUNITY_ICON

    embed = {
        'username': bot_name,
        'avatar_url': bot_avatar,
        'embeds': [
            {
                'title': f'Reinstated {punishment_noun(dinf)} on {target_name(dinf)}',
                'color': 7339950,
                'author': await embed_author(app, actor),
                'url': f'http://{HOST}/infractions/{str(dinf.id)}/',
                'thumbnail': {'url': target_avatar(dinf)},
                'footer': {'icon_url': GFLBANS_ICON, 'text': await _embed_host(app.state.db[MONGO_DB], dinf.server)},
                'timestamp': datetime.now(tz=UTC).strftime('%Y-%m-%dT%H:%M:%SZ'),
                'fields': [
                    {'name': 'Player', 'value': target_link(dinf), 'inline': True},
                    {'name': 'Duration', 'value': embed_duration(dinf), 'inline': True},
                    {'name': 'Reason', 'value': dinf.reason},
                ],
            }
        ],
    }

    if dinf.server is not None:
        srv = await DServer.from_id(app.state.db[MONGO_DB], dinf.server)
    else:
        srv = None

    if srv is not None and srv.infract_webhook is not None:
        async with app.state.aio_session.post(
            srv.infract_webhook + '?wait=true', headers={'User-Agent': f'{BRANDING} ({HOST}, {GB_VERSION})'}, json=embed
        ) as resp:
            try:
                resp.raise_for_status()
            except Exception:
                logger.error('Failed to post infraction to srv infract webhook', exc_info=True)

    if GLOBAL_INFRACTION_WEBHOOK is not None:
        async with app.state.aio_session.post(
            GLOBAL_INFRACTION_WEBHOOK + '?wait=true',
            headers={'User-Agent': f'{BRANDING} ({HOST}, {GB_VERSION})'},
            json=embed,
        ) as resp:
            try:
                resp.raise_for_status()
            except Exception:
                logger.error('Failed to post infraction to global infract webhook', exc_info=True)


async def discord_notify_purge_infraction(app, dinf: DInfraction, actor: Optional[ObjectId]):
    bot_name = f'{BRANDING}'
    bot_avatar = COMMUNITY_ICON

    embed = {
        'username': bot_name,
        'avatar_url': bot_avatar,
        'embeds': [
            {
                'title': f'Purged {punishment_noun(dinf)} on {target_name(dinf)}',
                'color': 16711680,  # Red color for purge
                'author': await embed_author(app, actor),
                'url': f'http://{HOST}/infractions/{str(dinf.id)}/',
                'thumbnail': {'url': target_avatar(dinf)},
                'footer': {'icon_url': GFLBANS_ICON, 'text': await _embed_host(app.state.db[MONGO_DB], dinf.server)},
                'timestamp': datetime.now(tz=UTC).strftime('%Y-%m-%dT%H:%M:%SZ'),
                'fields': [
                    {'name': 'Player', 'value': target_link(dinf), 'inline': True},
                    {'name': 'Duration', 'value': embed_duration(dinf), 'inline': True},
                    {'name': 'Reason', 'value': dinf.reason},
                ],
            }
        ],
    }

    if dinf.server is not None:
        srv = await DServer.from_id(app.state.db[MONGO_DB], dinf.server)
    else:
        srv = None

    if srv is not None and srv.infract_webhook is not None:
        async with app.state.aio_session.post(
            srv.infract_webhook + '?wait=true', headers={'User-Agent': f'{BRANDING} ({HOST}, {GB_VERSION})'}, json=embed
        ) as resp:
            try:
                resp.raise_for_status()
            except Exception:
                logger.error('Failed to post infraction to srv infract webhook', exc_info=True)

    if GLOBAL_INFRACTION_WEBHOOK is not None:
        async with app.state.aio_session.post(
            GLOBAL_INFRACTION_WEBHOOK + '?wait=true',
            headers={'User-Agent': f'{BRANDING} ({HOST}, {GB_VERSION})'},
            json=embed,
        ) as resp:
            try:
                resp.raise_for_status()
            except Exception:
                logger.error('Failed to post infraction to global infract webhook', exc_info=True)


# If true, the target is immune!
async def check_immunity(app, dinf: DInfraction, initiator_admin: Admin = None) -> bool:
    if dinf.user is None:
        return False

    try:
        target_admin = await load_admin_from_initiator(
            app, Initiator(gs_admin=PlayerObjNoIp(gs_service=dinf.user.gs_service, gs_id=dinf.user.gs_id))
        )
    except NoSuchAdminError:
        return False
    except ClientResponseError as e:
        logger.error('Error whilst getting loading admin permissions for immunity check', exc_info=e)
        raise HTTPException(detail='Internal Server Error', status_code=500)

    if (
        target_admin.permissions & PERMISSION_IMMUNE == PERMISSION_IMMUNE
        and initiator_admin is not None
        and initiator_admin.permissions & PERMISSION_SKIP_IMMUNITY != PERMISSION_SKIP_IMMUNITY
    ):
        return True

    return False
