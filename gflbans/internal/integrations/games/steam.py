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


# This will raise an exception if it isn't a number
def steam_validate_id(steamid64: str):
    if int(steamid64) & 0x0110000100000000 != 0x0110000100000000:
        raise ValueError('Bad SteamID64')

async def normalize_id(app, steamid: str) -> str:
    return await id64_or_none(app, steamid)
