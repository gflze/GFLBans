from bson import json_util
from datetime import datetime
from dateutil.tz import UTC
import json

from contextlib import suppress

from redis.exceptions import RedisError

from gflbans.internal.avatar import process_avatar
from gflbans.internal.config import MONGO_DB, STEAM_OPENID_ACCESS_TOKEN_LIFETIME
from gflbans.internal.log import logger


# Used in login
async def get_member_id_from_token(app, access_token: str):
    user_cache = app.state.db[MONGO_DB]['user_cache']
    response = await user_cache.find_one({'access_token': access_token})
    if response is None:
        return None
    elif (datetime.now(tz=UTC).replace(tzinfo=None) - response['created']).total_seconds() > STEAM_OPENID_ACCESS_TOKEN_LIFETIME or \
        (datetime.now(tz=UTC).replace(tzinfo=None) - response['last_validated']).total_seconds() > STEAM_OPENID_ACCESS_TOKEN_LIFETIME:
        user_cache.delete_one({'_id': response['_id']})
        logger.error('Entry expired', exc_info=True)
        raise
    return response['authed_as']


async def get_member_by_id(app, member_id: int):
    with suppress(RedisError):
        a = await app.state.ips_cache.get(str(member_id), 'user_cache')
        if a is not None:
            return a

    return await get_member_by_id_nc(app, member_id)


# A version of get_member_by_id that skips the cache
# Used for Admin()
async def get_member_by_id_nc(app, member_id: int):
    response = await app.state.db[MONGO_DB]['admin_cache'].find_one({'ips_user': member_id})

    if response is None:
        logger.debug(f'DB: no document for ips user {member_id}')
        return

    json_response = json.loads(json_util.dumps(response))

    with suppress(Exception):
            await app.state.ips_cache.set(str(member_id), json_response, 'user_cache',
                                expire_time=10 * 60)

    return json_response

# Wrapper around process_avatar for IPS photoUrl results
# as sometimes photoUrl doesn't return an HTTP url
# Returns a File or None if the url wasn't valid
async def ips_process_avatar(app, avatar_url):
    if avatar_url.startswith('data:image'):
        return None
    elif avatar_url.startswith('http'):
        return await process_avatar(app, avatar_url)
    elif avatar_url.startswith('//'):
        return await process_avatar(app, 'https:' + avatar_url)
    else:
        return None


# Gets an IPS member id from a game server id
def ips_get_member_id_from_gsid(gs_id):
    return int(gs_id) - 76561197960265728 # Convert Steam64 ID to 32, since mongodb doesnt like 64 bit numbers

# Gets a game server id from an IPS member id
def ips_get_gsid_from_member_id(member_id: int):
    return member_id + 76561197960265728

async def _get_groups(app):
    groups = await app.state.db[MONGO_DB]['groups'].find()

    if groups is None:
        logger.debug('DB: no collection of groups')
        return

    return json.loads(json_util.dumps(groups))

async def get_groups(app):
    with suppress(RedisError):
        a = await app.state.ips_cache.get('GROUPS', 'GLOBAL_GROUPS')
        if a is not None:
            return a

    r = await _get_groups(app)

    await app.state.ips_cache.set('GROUPS', r, 'GLOBAL_GROUPS', expire_time=5 * 60)

    return r
