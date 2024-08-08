from contextlib import suppress

from aredis import RedisError
from aredis.cache import IdentityGenerator

from gflbans.internal.config import STEAM_API_KEY
from gflbans.internal.log import logger
from gflbans.internal.search import id64_or_none


class SteamIdentityGenerator(IdentityGenerator):
    def generate(self, key, typ):
        return 'Steam::%s:%s' % (typ, key)


async def _get_steam_user_info(app, steamid64: str):
    if STEAM_API_KEY is None:
        raise NotImplementedError('Tried to call the steam api without an api key.')

    with suppress(RedisError):
        a = await app.state.steam_cache.get(steamid64, 'user_cache')
        if a is not None:
            return a

    async with app.state.aio_session.get('https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/',
                                     params={'key': STEAM_API_KEY, 'steamids': steamid64, 'format': 'json'}) as resp:
        try:
            resp.raise_for_status()
        except Exception:
            logger.error('Steam API error!', exc_info=True)
            raise

        j = await resp.json()

        ply = j['response']['players'][0]

        with suppress(Exception):
            await app.state.steam_cache.set(steamid64, ply, 'user_cache', expire_time=(3600 * 24))

        return ply


async def get_steam_user_info(app, steamid64: str):
    info = await _get_steam_user_info(app, steamid64)

    return {'avatar_url': info['avatarfull'], 'name': info['personaname']}


async def _get_steam_multiple_user_info(app, steamid64_list: list[str]):
    if STEAM_API_KEY is None:
        raise NotImplementedError('Tried to call the steam api without an api key.')
    
    users = dict()

    for steamid64 in steamid64_list:
        with suppress(RedisError):
            a = await app.state.steam_cache.get(steamid64, 'user_cache')
            if a is not None:
                users[steamid64] = a
                steamid64_list.remove(steamid64)

    if len(steamid64_list) == 0:
        return users
    
    batched_steam_ids = ""
    for steamid64 in steamid64_list:
        batched_steam_ids += f',{steamid64}'
    batched_steam_ids = batched_steam_ids[1:] # Remove comma at start

    async with app.state.aio_session.get('https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/',
                                     params={'key': STEAM_API_KEY, 'steamids': batched_steam_ids, 'format': 'json'}) as resp:
        try:
            resp.raise_for_status()
        except Exception:
            logger.error('Steam API error!', exc_info=True)
            raise

        j = await resp.json()

        for ply in j['response']['players']:
            users[ply['steamid']] = ply
            with suppress(Exception):
                await app.state.steam_cache.set(steamid64, ply, 'user_cache', expire_time=(3600 * 24))

        return users


async def get_steam_multiple_user_info(app, steamid64_list: list[str]):
    info_list = await _get_steam_multiple_user_info(app, steamid64_list)
    user_list = dict()
    for steamid, info in info_list.items():
        user_list[steamid] = {'avatar_url': info['avatarfull'], 'name': info['personaname']}

    return user_list


# This will raise an exception if it isn't a number
def steam_validate_id(steamid64: str):
    if int(steamid64) & 0x0110000100000000 != 0x0110000100000000:
        raise ValueError('Bad SteamID64')

async def normalize_id(app, steamid: str) -> str:
    return await id64_or_none(app, steamid)
