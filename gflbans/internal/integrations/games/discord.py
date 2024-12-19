import asyncio
import math
from contextlib import suppress

from redis.exceptions import RedisError

from gflbans.internal.config import DISCORD_BOT_TOKEN
from gflbans.internal.log import logger


async def _get_discord_user_info(app, discord_id: str, t=0):
    if DISCORD_BOT_TOKEN is None:
        logger.debug('Tried to call discord api without a discord token!')
        raise NotImplementedError('Tried to call the discord api without a bot token.')

    with suppress(RedisError):
        a = await app.state.discord_cache.get(discord_id, 'user_cache')
        if a is not None:
            logger.debug('Returning cached discord user info')
            return a

    async with app.state.aio_session.get(
        f'https://discord.com/api/users/{discord_id}',
        headers={'Authorization': f'Bot {DISCORD_BOT_TOKEN}', 'User-Agent': 'gflbans (bans.gflclan.com, 1.0)'},
    ) as resp:
        if resp.status == 429 and t <= 3:
            logger.error('Rate limited by Discord!')
            # Retry after waiting a bit
            a = await resp.json()
            if 'retry_after' in a:
                await asyncio.sleep(math.ceil(int(a['retry_after']) / 1000))
            else:
                await asyncio.sleep(5)
            return await _get_discord_user_info(app, discord_id, t=t + 1)
        try:
            resp.raise_for_status()
        except Exception:
            logger.error('Discord request error!', exc_info=True)
            raise
        j = await resp.json()

        with suppress(Exception):
            await app.state.discord_cache.set(discord_id, j, 'user_cache', expire_time=(3600 * 24))

        return j


async def get_discord_user_info(app, discord_id: str):
    info = await _get_discord_user_info(app, discord_id)

    return {
        'avatar_url': f'https://cdn.discordapp.com/avatars/{info["id"]}/{info["avatar"]}.png',
        'name': f'{info["username"]}#{info["discriminator"]}',
    }


# This will raise an exception if it isn't a number
def discord_validate_id(discord_id: str):
    int(discord_id)


async def normalize_id(app, discord_id: str) -> str:
    return discord_id
