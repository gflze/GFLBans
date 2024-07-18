from bson import json_util
import json

from contextlib import suppress
from typing import Tuple

from aredis import RedisError

from aredis.cache import IdentityGenerator

from gflbans.internal.avatar import process_avatar
from gflbans.internal.config import FORUMS_OAUTH_TOKEN_URL, FORUMS_OAUTH_CLIENT_SECRET, FORUMS_OAUTH_CLIENT_ID, HOST, \
    FORUMS_API_PATH, MONGO_DB
from gflbans.internal.errors import NoSuchAdminError
from gflbans.internal.log import logger
from gflbans.internal.utils import slash_fix


class IPSIdentityGenerator(IdentityGenerator):
    def generate(self, key, typ):
        return 'IPS::%s:%s' % (typ, key)


async def get_token(app):
    with suppress(RedisError):
        a = await app.state.ips_cache.get('primary_token', 'token_cache')
        if a is not None and 'access_token' in a:
            return a['access_token']

    async with app.state.aio_session.post(FORUMS_OAUTH_TOKEN_URL,
                                    data={'grant_type': 'client_credentials',
                                          'client_id': FORUMS_OAUTH_CLIENT_ID,
                                          'client_secret': FORUMS_OAUTH_CLIENT_SECRET,
                                          'scope': 'system'}) as resp:
        try:
            resp.raise_for_status()
        except Exception:
            logger.error('IPS API Error!', exc_info=True)
            raise

        j = await resp.json()

        if 'expires_in' not in j:
            j['expires_in'] = 604800

        with suppress(Exception):
            await app.state.ips_cache.set('primary_token', {'access_token': j['access_token']}, 'token_cache',
                                expire_time=(j['expires_in'] - 30))

        return j['access_token']

# Used in login
async def get_user_token(app, auth_token: str):
    async with app.state.aio_session.post(FORUMS_OAUTH_TOKEN_URL, data={'grant_type': 'authorization_code',
                                                                  'code': auth_token,
                                                                  'redirect_uri': f'https://{HOST}/login/finish',
                                                                  'client_id': FORUMS_OAUTH_CLIENT_ID,
                                                                  'client_secret': FORUMS_OAUTH_CLIENT_SECRET}) as r:
        try:
            r.raise_for_status()
        except Exception:
            logger.error(f'IPS API Error', exc_info=True)
            raise

        j = await r.json()
        return j


async def refresh_access_token(app, refresh_token: str) -> Tuple[str, str, str]:
    async with app.state.aio_session.post(FORUMS_OAUTH_TOKEN_URL,
                                    data={'grant_type': 'refresh_token', 'refresh_token': refresh_token}) as resp:
        try:
            resp.raise_for_status()
        except Exception:
            logger.error('IPS API Error!', exc_info=True)
            raise

        j = await resp.json()

        if 'expires_in' not in j:
            j['expires_in'] = 604800

        if 'refresh_token' not in j:
            j['refresh_token'] = None

        return j['access_token'], j['expires_in'], j['refresh_token']

# Used in login
async def get_member_id_from_token(app, access_token: str):
    async with app.state.aio_session.get(f'{slash_fix(FORUMS_API_PATH)}core/me',
                                   headers={'Authorization': f'Bearer {access_token}'}) as resp:
        try:
            resp.raise_for_status()
        except Exception:
            logger.error('IPS API Error!', exc_info=True)
            raise

        j = await resp.json()
        return j['id']


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
async def ips_get_member_id_from_gsid(app, gs_service, gs_id):
    return int(gs_id) - 76561197960265728 # Convert Steam64 ID to 32, since mongodb doesnt like 64 bit numbers

async def discord_ips_get_member_id_from_gsid(app, gs_id):
    token = await get_token(app)

    async with app.state.aio_session.get(f'{slash_fix(FORUMS_API_PATH)}discordapi/idof/{gs_id}',
                                   headers={'Authorization': f'Bearer {token}'}) as resp:

        if resp.status == 404:
            raise NoSuchAdminError('No such admin.')

        try:
            resp.raise_for_status()
        except Exception:
            logger.error('IPS API Error!', exc_info=True)
            raise

        r = await resp.json()
        return r


async def steam_ips_get_member_id_from_gsid(app, gs_id):
    token = await get_token(app)

    async with app.state.aio_session.get(f'{slash_fix(FORUMS_API_PATH)}steamlogin/idof/{gs_id}',
                                   headers={'Authorization': f'Bearer {token}'}) as resp:
        if resp.status == 404:
            raise NoSuchAdminError('No such admin.')

        try:
            resp.raise_for_status()
        except Exception:
            logger.error('IPS API Error!', exc_info=True)
            raise

        r = await resp.json()
        return r


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
