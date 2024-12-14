import asyncio
from datetime import datetime, timedelta
from gflbans.internal.database.admin import Admin
from gflbans.internal.errors import NoSuchAdminError
from gflbans.internal.integrations.ips import ips_get_gsid_from_member_id
from gflbans.internal.kv import get_var
from gflbans.internal.pyapi_utils import load_admin_from_initiator
from typing import List, Union, Optional
from gflbans.internal.flags import PERMISSION_IMMUNE, PERMISSION_SKIP_IMMUNITY, str2permflag
from bson import ObjectId
from dateutil.tz import UTC
from pydantic import PositiveInt
from aiohttp import ClientResponseError
from fastapi import HTTPException

# This function does no permission checks. It merely constructs a DInfraction object without saving it
# with the desired parameters
from starlette.requests import Request

from gflbans.api_util import construct_ci_resp
from gflbans.internal.asn import check_vpn, VPN_YES, VPN_CLOUD
from gflbans.internal.avatar import process_avatar
from gflbans.internal.config import HOST, MONGO_DB, GLOBAL_INFRACTION_WEBHOOK, GFLBANS_ICON, COMMUNITY_ICON
from gflbans.internal.constants import SERVER_KEY
from gflbans.internal.database.common import DFile
from gflbans.internal.database.infraction import DInfraction, DUser, build_query_dict
from gflbans.internal.database.rpc import DRPCPlayerUpdated
from gflbans.internal.database.server import DServer
from gflbans.internal.database.task import DTask
from gflbans.internal.database.tiering_policy import DTieringPolicy
from gflbans.internal.flags import INFRACTION_ADMIN_CHAT_BLOCK, INFRACTION_CALL_ADMIN_BAN, \
    INFRACTION_CHAT_BLOCK, INFRACTION_VOICE_BLOCK, PERMISSION_CREATE_INFRACTION, PERMISSION_SCOPE_GLOBAL, \
    PERMISSION_SCOPE_SUPER_GLOBAL, scope_to_flag, str2pflag, INFRACTION_SESSION, INFRACTION_PERMANENT, \
    INFRACTION_DEC_ONLINE_ONLY, INFRACTION_WEB, INFRACTION_AUTO_TIER, INFRACTION_SYSTEM, INFRACTION_REMOVED, \
    INFRACTION_VPN, INFRACTION_GLOBAL, INFRACTION_SUPER_GLOBAL, INFRACTION_BAN, str2pflag, INFRACTION_ITEM_BLOCK
from gflbans.internal.integrations.games import get_user_info, validate_id_ex
from gflbans.internal.log import logger
from gflbans.internal.models.api import Initiator, PlayerObjSimple, PositiveIntIncl0, PlayerObjNoIp
from humanize import naturaldelta

def filter_badchars(s):
    return s.replace('\n', ' ')


def create_dinfraction(player: PlayerObjSimple, reason: str, scope: str, punishments: List,
                       session: bool = False,
                       created: int = None, duration: int = None, admin: ObjectId = None, policy_id: str = None,
                       dec_online: bool = False, server: ObjectId = None) -> DInfraction:
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
    elif dec_online:
        dinf.original_time = duration
        dinf.time_left = duration
        dinf.flags |= INFRACTION_DEC_ONLINE_ONLY
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

    if policy_id:
        dinf.flags |= INFRACTION_AUTO_TIER
        dinf.policy_id = policy_id

    if admin:
        dinf.admin = admin
    else:
        dinf.flags |= INFRACTION_SYSTEM

    return dinf


# Do the policy thing and call the above function
async def create_dinfraction_with_policy(app, actor_type: int, player: PlayerObjSimple, scope: str,
                                         policy_id: str, admin: ObjectId = None, reason_override: str = None,
                                         actor_id: ObjectId = None, other_pol: List[str] = None,
                                         server_override: Optional[ObjectId] = None) -> DInfraction:
    # load the policy object
    policy = await DTieringPolicy.from_id(app.state.db[MONGO_DB], policy_id)

    if policy is None:
        raise TypeError('Expected a DTieringPolicy, got None')

    # Build a dict and get the tier
    if server_override is None:
        q = build_query_dict(actor_type, str(actor_id), player.gs_service, player.gs_id, player.ip,
                             not policy.include_other_servers, False)
    else:
        q = build_query_dict(SERVER_KEY, str(server_override), player.gs_service, player.gs_id, player.ip,
                             not policy.include_other_servers, False)

    oj = {'policy_id': ObjectId(policy_id)}

    if other_pol is not None:
        oj = {'$or': [
            oj
        ]}

        for op in other_pol:
            oj['$or'].append({'policy_id': ObjectId(op)})

    # Special case: I don't want to consider expired warns in the tier because it confused some people
    q = {
        '$and': [   
            q,
            {'flags': {'$bitsAllSet': INFRACTION_AUTO_TIER}},
            oj,
            {'flags': {'$bitsAllClear': INFRACTION_SESSION | INFRACTION_REMOVED}},
            {'created': {'$gte': datetime.now(tz=UTC).timestamp() - policy.tier_ttl}},
            {'$or': {
                    {'flags': {'$bitsAnySet': INFRACTION_BAN | INFRACTION_VOICE_BLOCK | INFRACTION_CHAT_BLOCK | INFRACTION_CALL_ADMIN_BAN | INFRACTION_ADMIN_CHAT_BLOCK | INFRACTION_ITEM_BLOCK}},
                    {'$or': {
                        {'flags': {'$bitsAllSet': INFRACTION_PERMANENT}},
                        {'time_left': {'$gt': 0}},
                        {'expires': {'$gt': datetime.now(tz=UTC).timestamp()}}
                    }}
                }
            }
        ]
    }

    t = await app.state.db[MONGO_DB].infractions.count_documents(q)

    tier_idx = policy.tiers[t - 1] if t <= len(policy.tiers) else len(policy.tiers) - 1

    tier = policy.tiers[tier_idx]

    r = reason_override if reason_override else tier.reason

    if server_override is not None:
        server = server_override
    elif actor_type == SERVER_KEY:
        server = actor_id
    else:
        server = None

    return create_dinfraction(player, r, scope, tier.punishments, duration=tier.duration, admin=admin,
                              dec_online=tier.dec_online, server=server, policy_id=policy_id)


async def get_user_data(app, infraction_id: ObjectId, reschedule_on_fail=False):
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
            ''' If avatar failed but everything else was fine, just dont store an avatar in the infraction but store name
                still. This should hopefully only happen in rare cases where Steam deletes the picture on the backend but
                for some reason leaves the deleted URL as the person's steam avatar. '''
            logger.warning('get_user_data failed to find an avatar. Leaving as empty in the infraction.', exc_info=e)
            pass

        await dinf.update_field(app.state.db[MONGO_DB], 'user', duser)

        await discord_notify_create_infraction(app, dinf)
    except Exception as e:
        logger.error('get_user_data failed!', exc_info=e)
        if reschedule_on_fail:
            logger.info(f'Rescheduling get_user_data call for {str(infraction_id)})...')
            dt = DTask(run_at=datetime.now(tz=UTC).timestamp() + 5, task_data={'i_id': infraction_id},
                       ev_handler='get_user_data')
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

        if vpn_state == VPN_YES or vpn_state == VPN_CLOUD:
            logger.info(f'{dinf.ip} is a vpn or cloud gaming IP address.')

            await dinf.add_bit_flag(app.state.db[MONGO_DB], 'flags', INFRACTION_VPN)
    except Exception as e:
        logger.error('get_vpn_data failed!', exc_info=e)
        if reschedule_on_fail:
            logger.info(f'Rescheduling get_vpn_data call for {str(infraction_id)})...')
            dt = DTask(run_at=datetime.now(tz=UTC).timestamp() + 5, task_data={'i_id': infraction_id},
                       ev_handler='get_vpn_data')
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


async def policy_name(app, pol_ref: Optional[ObjectId]) -> str:
    if pol_ref is None:
        return 'No Policy'

    dpol = await DTieringPolicy.from_id(app.state.db[MONGO_DB], pol_ref)
    
    if dpol is None:
        return 'UNKNOWN'
    
    return dpol.name


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


async def modify_infraction(app, target: ObjectId, author: Union[ObjectId, str, None] = None,
                            make_session: bool = False, make_permanent: bool = False,
                            expiration: Optional[PositiveInt] = None, time_left: Optional[PositiveIntIncl0] = None,
                            policy_id: Union[ObjectId, None, bool] = None, server: Optional[ObjectId] = None,
                            reason: Optional[str] = None, set_removal_state: Optional[bool] = None,
                            removed_by: Optional[ObjectId] = None,
                            removal_reason: Optional[str] = None, punishments: Optional[List] = None,
                            scope: Optional[str] = None, vpn: Optional[bool] = None, make_web: bool = False,
                            reuse_dinf: DInfraction = None, actor: Optional[ObjectId] = None):
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
        changes[var] = {
            'old': old,
            'new': new
        }

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
                uwu('Owner', await load_admin_from_initiator(app, Initiator(mongo_id=str(dinf.admin) if dinf.admin is not None else None)).name,
                             await load_admin_from_initiator(app, Initiator(mongo_id=str(author))).name)

            commit_list.append(dinf.update_field(db, 'admin', author))
            commit_list.append(dinf.remove_bit_flag(db, 'flags', INFRACTION_SYSTEM))
        else:
            raise ValueError('Attempted to do an author update with an unsupported author type')

    # Handle changing of the expiration properties of the infraction
    fl = ['expires', 'time_left', 'original_time']
    fl2 = [INFRACTION_SESSION, INFRACTION_PERMANENT, INFRACTION_DEC_ONLINE_ONLY]

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
        elif dinf.flags & INFRACTION_DEC_ONLINE_ONLY == INFRACTION_DEC_ONLINE_ONLY:
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
            raise ValueError('Cannot set a ban to dec online only')

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
        commit_list.append(dinf.add_bit_flag(db, 'flags', INFRACTION_DEC_ONLINE_ONLY))

    # Handle policy_id set or remove
    if policy_id is not None:
        if isinstance(policy_id, bool):
            uwu('Tiering Policy', await policy_name(app, dinf.policy_id), 'None')
            commit_list.append(dinf.unset_field(db, 'policy_id'))
            commit_list.append(dinf.remove_bit_flag(db, 'flags', INFRACTION_AUTO_TIER))
        elif isinstance(policy_id, ObjectId):
            uwu('Tiering Policy', await policy_name(app, dinf.policy_id), await policy_name(app, policy_id))
            commit_list.append(dinf.update_field(db, 'policy_id', policy_id))
            commit_list.append(dinf.add_bit_flag(db, 'flags', INFRACTION_AUTO_TIER))
        else:
            raise ValueError('Tried to specify a policy ID using an unknown identifier type')

    if make_web:
        uwu('Server', await _embed_host(app.state.db[MONGO_DB], dinf.server), 'GFLBans Web')
        commit_list.append(dinf.unset_field(db, 'server'))
        commit_list.append(dinf.add_bit_flag(db, 'flags', INFRACTION_WEB))
    elif server is not None:
        uwu('Server', await _embed_host(app.state.db[MONGO_DB], dinf.server), await _embed_host(app.state.db[MONGO_DB], server))
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
        elif a  == 'admin_chat_block':
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
        if 'ban' in punishments and dinf.flags & INFRACTION_DEC_ONLINE_ONLY == INFRACTION_DEC_ONLINE_ONLY:
            raise ValueError('Cannot make a dec online only infraction into a ban')
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
        elif dinf.flags & INFRACTION_SUPER_GLOBAL == INFRACTION_SUPER_GLOBAL:
            uwu('Scope', 'Community', scope)
        else:
            uwu('Scope', 'Server Only', scope)

        commit_list.append(dinf.remove_bit_flag(db, 'flags', INFRACTION_GLOBAL | INFRACTION_SUPER_GLOBAL))

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

        local = build_query_dict(SERVER_KEY, str(s.id), gs_service=user.gs_service, gs_id=user.gs_id,
                                 ignore_others=True, active_only=True)

        glob = build_query_dict(SERVER_KEY, str(s.id), gs_service=user.gs_service, gs_id=user.gs_id,
                                ignore_others=False, active_only=True)

        ci_resp_local = await construct_ci_resp(app.state.db[MONGO_DB], local)
        ci_resp_global = await construct_ci_resp(app.state.db[MONGO_DB], glob)

        r = DRPCPlayerUpdated(target_type='player', target_payload=PlayerObjNoIp(gs_service=user.gs_service,
                                                                                 gs_id=user.gs_id), local=ci_resp_local,
                              glob=ci_resp_global, time=datetime.now(tz=UTC), target=s.id)

        await r.commit(app.state.db[MONGO_DB])

    async def load_ip(s, ip):
        logger.debug('enter load_ip')

        local = build_query_dict(SERVER_KEY, str(s.id), ip=ip, ignore_others=True, active_only=True)

        glob = build_query_dict(SERVER_KEY, str(s.id), ip=ip, ignore_others=False, active_only=True)

        ci_resp_local = await construct_ci_resp(app.state.db[MONGO_DB], local)
        ci_resp_global = await construct_ci_resp(app.state.db[MONGO_DB], glob)

        r = DRPCPlayerUpdated(target_type='ip', target_payload=ip, local=ci_resp_local,
                              glob=ci_resp_global, time=datetime.now(tz=UTC), target=s.id)

        await r.commit(app.state.db[MONGO_DB])

    async for srv in DServer.from_query_ex(app.state.db[MONGO_DB], {}):
        if dinf.user is not None:
            gathers.append(load_user(srv, dinf.user))

        if dinf.ip:
            gathers.append(load_ip(srv, dinf.ip))

    await asyncio.gather(*gathers)

_nouns = {
    INFRACTION_VOICE_BLOCK: 'Voice Chat Block',
    INFRACTION_CHAT_BLOCK: 'Text Chat Block',
    INFRACTION_BAN: 'Ban',
    INFRACTION_ADMIN_CHAT_BLOCK: 'Admin Chat Block',
    INFRACTION_CALL_ADMIN_BAN: 'Call Admin Block',
    INFRACTION_VOICE_BLOCK | INFRACTION_CHAT_BLOCK: 'Silence',
    INFRACTION_ITEM_BLOCK: 'Item Block'
}

def punishment_noun(dinf: DInfraction) -> str:
    for k, v in _nouns.items():
        others = (INFRACTION_VOICE_BLOCK | INFRACTION_CHAT_BLOCK | INFRACTION_BAN | INFRACTION_ADMIN_CHAT_BLOCK | INFRACTION_CALL_ADMIN_BAN | INFRACTION_ITEM_BLOCK) & ~k

        if dinf.flags & k == k and dinf.flags & others == 0:
            return v
        
        if dinf.flags & (INFRACTION_VOICE_BLOCK | INFRACTION_CHAT_BLOCK | INFRACTION_BAN | INFRACTION_ADMIN_CHAT_BLOCK | INFRACTION_CALL_ADMIN_BAN | INFRACTION_ITEM_BLOCK) == 0:
            return 'Warning'
        
    return 'Infraction'


def get_permissions(dinf: DInfraction) -> int:
    i = PERMISSION_CREATE_INFRACTION

    for pun_str, pun_flag in str2pflag.items():
        if dinf.flags & pun_flag == pun_flag:
            i |= str2permflag[pun_str]

    if dinf.flags & INFRACTION_GLOBAL == INFRACTION_GLOBAL:
        i |= PERMISSION_SCOPE_GLOBAL

    if dinf.flags & INFRACTION_SUPER_GLOBAL == INFRACTION_SUPER_GLOBAL:
        i |= PERMISSION_SCOPE_SUPER_GLOBAL

    return i


async def embed_author(app, admin_id: Optional[ObjectId]):
    if admin_id is not None:
        adm = await load_admin_from_initiator(app, Initiator(mongo_id=str(admin_id)))

        await adm.fetch_details(app)

        return {
            'name': adm.name,
            'icon_url': f'http://{HOST}/static/images/fallback_av.png' if adm.avatar is None else f'http://{HOST}/file/uploads/{adm.avatar.gridfs_file}/avatar.webp',
            'url': f'https://steamcommunity.com/profiles/{ips_get_gsid_from_member_id(adm.ips_id)}/'
        }
    else:
        return {
            'name': 'System',
            'icon_url': f'http://{HOST}/static/images/fallback_av.png'
        }


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
        return f'[{name}](https://steamcommunity.com/profiles/{dinf.user.gs_id})'
    else:
        return name


def embed_duration(dinf: DInfraction):
    if dinf.original_time is not None:
        return naturaldelta(timedelta(seconds=dinf.original_time)).capitalize()
    elif dinf.expires is not None:
        return naturaldelta(timedelta(seconds=dinf.expires - dinf.created)).capitalize()
    elif dinf.flags & INFRACTION_PERMANENT == INFRACTION_PERMANENT:
        return 'Infinite'
    elif dinf.flags & INFRACTION_SESSION == INFRACTION_SESSION:
        return 'Session'
    else:
        return 'OOPS, INVALID!'


async def discord_notify_create_infraction(app, dinf: DInfraction):
    bot_name, bot_avatar = await get_var(app.state.db[MONGO_DB], 'bot.name', 'GFLBans Bot'), await get_var(app.state.db[MONGO_DB], 'bot.avatar', COMMUNITY_ICON)

    embed = {
        'username': bot_name,
        'avatar_url': bot_avatar,
        'embeds': [
            {
                'title': f'New {punishment_noun(dinf)} on {target_name(dinf)}',
                'color': 9371903,
                'author': await embed_author(app, dinf.admin),
                'url': f'http://{HOST}/infractions/{str(dinf.id)}/',
                'thumbnail': {
                    'url': target_avatar(dinf)
                },
                'footer': {
                    'icon_url': GFLBANS_ICON,
                    'text': await _embed_host(app.state.db[MONGO_DB], dinf.server)
                },
                'timestamp': datetime.fromtimestamp(dinf.created, tz=UTC).strftime('%Y-%m-%dT%H:%M:%SZ'),
                'fields': [
                    {
                        'name': 'Player',
                        'value': target_link(dinf),
                        'inline': True
                    },
                    {
                        'name': 'Duration',
                        'value': embed_duration(dinf),
                        'inline': True
                    },
                    {
                        'name': 'Reason',
                        'value': dinf.reason
                    }
                ]
            }
        ]
    }

    if dinf.server is not None:
        srv = await DServer.from_id(app.state.db[MONGO_DB], dinf.server)
    else:
        srv = None
    
    if srv is not None and srv.infract_webhook is not None:
        async with app.state.aio_session.post(srv.infract_webhook + '?wait=true', headers={'User-Agent': 'gflbans (gflclan.com, 1.0)'}, json=embed) as resp:
            try:
                resp.raise_for_status()
            except Exception:
                logger.error('Failed to post infraction to srv infract webhook', exc_info=True)
    
    if GLOBAL_INFRACTION_WEBHOOK is not None:
        async with app.state.aio_session.post(GLOBAL_INFRACTION_WEBHOOK + '?wait=true', headers={'User-Agent': 'gflbans (gflclan.com, 1.0)'}, json=embed) as resp:
            try:
                resp.raise_for_status()
            except Exception:
                logger.error('Failed to post infraction to global infract webhook', exc_info=True)


async def discord_notify_edit_infraction(app, dinf: DInfraction, editor: Optional[ObjectId], changes):
    bot_name, bot_avatar = await get_var(app.state.db[MONGO_DB], 'bot.name', 'GFLBans Bot'), await get_var(app.state.db[MONGO_DB], 'bot.avatar', COMMUNITY_ICON)

    embed = {
        'username': bot_name,
        'avatar_url': bot_avatar,
        'embeds': [
            {
                'title': f'{punishment_noun(dinf)} on {target_name(dinf)} Updated',
                'color': 1104124,
                'author': await embed_author(app, editor),
                'url': f'http://{HOST}/infractions/{str(dinf.id)}/',
                'thumbnail': {
                    'url': target_avatar(dinf)
                },
                'footer': {
                    'icon_url': GFLBANS_ICON,
                    'text': await _embed_host(app.state.db[MONGO_DB], dinf.server)
                },
                'timestamp': datetime.fromtimestamp(dinf.created, tz=UTC).strftime('%Y-%m-%dT%H:%M:%SZ'),
                'fields': []
            }
        ]
    }

    for k, v in changes.items():
        embed['embeds'][0]['fields'].append({
            'name': k,
            'value': f'~~{v["old"]}~~ → {v["new"]}'
        })

    if dinf.server is not None:
        srv = await DServer.from_id(app.state.db[MONGO_DB], dinf.server)
    else:
        srv = None
    
    if srv is not None and srv.infract_webhook is not None:
        async with app.state.aio_session.post(srv.infract_webhook + '?wait=true', headers={'User-Agent': 'gflbans (gflclan.com, 1.0)'}, json=embed) as resp:
            try:
                resp.raise_for_status()
            except Exception:
                logger.error('Failed to post infraction to srv infract webhook', exc_info=True)
    
    if GLOBAL_INFRACTION_WEBHOOK is not None:
        async with app.state.aio_session.post(GLOBAL_INFRACTION_WEBHOOK + '?wait=true', headers={'User-Agent': 'gflbans (gflclan.com, 1.0)'}, json=embed) as resp:
            try:
                resp.raise_for_status()
            except Exception:
                logger.error('Failed to post infraction to global infract webhook', exc_info=True)


async def discord_notify_revoke_infraction(app, dinf: DInfraction, actor: Optional[ObjectId]):
    bot_name, bot_avatar = await get_var(app.state.db[MONGO_DB], 'bot.name', 'GFLBans Bot'), await get_var(app.state.db[MONGO_DB], 'bot.avatar', COMMUNITY_ICON)

    embed = {
        'username': bot_name,
        'avatar_url': bot_avatar,
        'embeds': [
            {
                'title': f'Revoked {punishment_noun(dinf)} on {target_name(dinf)}',
                'color': 16711792,
                'author': await embed_author(app, actor),
                'url': f'http://{HOST}/infractions/{str(dinf.id)}/',
                'thumbnail': {
                    'url': target_avatar(dinf)
                },
                'footer': {
                    'icon_url': GFLBANS_ICON,
                    'text': await _embed_host(app.state.db[MONGO_DB], dinf.server)
                },
                'timestamp': datetime.fromtimestamp(dinf.removed, tz=UTC).strftime('%Y-%m-%dT%H:%M:%SZ'),
                'fields': [
                    {
                        'name': 'Player',
                        'value': target_link(dinf),
                        'inline': True
                    },
                    {
                        'name': 'Duration',
                        'value': embed_duration(dinf),
                        'inline': True
                    },
                    {
                        'name': 'Reason',
                        'value': dinf.reason
                    },
                    {
                        "name": "Removal Reason",
                        "value": dinf.ureason
                    }
                ]
            }
        ]
    }

    if dinf.server is not None:
        srv = await DServer.from_id(app.state.db[MONGO_DB], dinf.server)
    else:
        srv = None
    
    if srv is not None and srv.infract_webhook is not None:
        async with app.state.aio_session.post(srv.infract_webhook + '?wait=true', headers={'User-Agent': 'gflbans (gflclan.com, 1.0)'}, json=embed) as resp:
            try:
                resp.raise_for_status()
            except Exception:
                logger.error('Failed to post infraction to srv infract webhook', exc_info=True)
    
    if GLOBAL_INFRACTION_WEBHOOK is not None:
        async with app.state.aio_session.post(GLOBAL_INFRACTION_WEBHOOK + '?wait=true', headers={'User-Agent': 'gflbans (gflclan.com, 1.0)'}, json=embed) as resp:
            try:
                resp.raise_for_status()
            except Exception:
                logger.error('Failed to post infraction to global infract webhook', exc_info=True)


async def discord_notify_reinst_infraction(app, dinf: DInfraction, actor: Optional[ObjectId]):
    bot_name, bot_avatar = await get_var(app.state.db[MONGO_DB], 'bot.name', 'GFLBans Bot'), await get_var(app.state.db[MONGO_DB], 'bot.avatar', COMMUNITY_ICON)

    embed = {
        'username': bot_name,
        'avatar_url': bot_avatar,
        'embeds': [
            {
                'title': f'Reinstated {punishment_noun(dinf)} on {target_name(dinf)}',
                'color': 7339950,
                'author': await embed_author(app, actor),
                'url': f'http://{HOST}/infractions/{str(dinf.id)}/',
                'thumbnail': {
                    'url': target_avatar(dinf)
                },
                'footer': {
                    'icon_url': GFLBANS_ICON,
                    'text': await _embed_host(app.state.db[MONGO_DB], dinf.server)
                },
                'timestamp': datetime.now(tz=UTC).strftime('%Y-%m-%dT%H:%M:%SZ'),
                'fields': [
                    {
                        'name': 'Player',
                        'value': target_link(dinf),
                        'inline': True
                    },
                    {
                        'name': 'Duration',
                        'value': embed_duration(dinf),
                        'inline': True
                    },
                    {
                        'name': 'Reason',
                        'value': dinf.reason
                    }
                ]
            }
        ]
    }

    if dinf.server is not None:
        srv = await DServer.from_id(app.state.db[MONGO_DB], dinf.server)
    else:
        srv = None
    
    if srv is not None and srv.infract_webhook is not None:
        async with app.state.aio_session.post(srv.infract_webhook + '?wait=true', headers={'User-Agent': 'gflbans (gflclan.com, 1.0)'}, json=embed) as resp:
            try:
                resp.raise_for_status()
            except Exception:
                logger.error('Failed to post infraction to srv infract webhook', exc_info=True)
    
    if GLOBAL_INFRACTION_WEBHOOK is not None:
        async with app.state.aio_session.post(GLOBAL_INFRACTION_WEBHOOK + '?wait=true', headers={'User-Agent': 'gflbans (gflclan.com, 1.0)'}, json=embed) as resp:
            try:
                resp.raise_for_status()
            except Exception:
                logger.error('Failed to post infraction to global infract webhook', exc_info=True)

# If true, the target is immune!
async def check_immunity(app, dinf: DInfraction, initiator_admin: Admin = None) -> bool:
    if dinf.user is None:
        return False

    try:
        target_admin = await load_admin_from_initiator(app, Initiator(gs_admin=PlayerObjNoIp(
            gs_service=dinf.user.gs_service, gs_id=dinf.user.gs_id)))
    except NoSuchAdminError:
        return False
    except ClientResponseError as e:
        logger.error('Error whilst communicating with the forums', exc_info=e)
        raise HTTPException(detail='Internal Server Error', status_code=500)

    if target_admin.permissions & PERMISSION_IMMUNE == PERMISSION_IMMUNE and \
            initiator_admin is not None and \
            initiator_admin.permissions & PERMISSION_SKIP_IMMUNITY != PERMISSION_SKIP_IMMUNITY:
        return True

    return False
