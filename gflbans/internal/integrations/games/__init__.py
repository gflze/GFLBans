from gflbans.internal.integrations.games.discord import discord_validate_id, get_discord_user_info
from gflbans.internal.integrations.games.steam import get_steam_user_info, steam_validate_id
from gflbans.internal.integrations.games.steam import normalize_id as discord_normalize
from gflbans.internal.integrations.games.steam import normalize_id as steam_normalize
from gflbans.internal.models.api import PlayerObjNoIp


async def get_user_info(app, service, gsid):
    if service == 'steam':
        return await get_steam_user_info(app, gsid)
    elif service == 'discord':
        return await get_discord_user_info(app, gsid)
    else:
        raise NotImplementedError(f'Retrieving user info from {service} is currently unsupported.')


SUPPORTED_SERVICES = ['steam', 'discord']


def validate_id(svc, gsid):
    if svc not in SUPPORTED_SERVICES:
        raise ValueError(f'{svc} is not currently supported.')

    if svc == 'steam':
        steam_validate_id(gsid)
    elif svc == 'discord':
        discord_validate_id(gsid)


def validate_id_ex(ply: PlayerObjNoIp):
    validate_id(ply.gs_service, ply.gs_id)


async def get_url(svc, gsid):
    if svc == 'steam':
        return f'https://steamcommunity.com/profiles/{gsid}'
    else:
        raise NotImplementedError('Not supported for this backend')


async def normalize_id(app, svc: str, gsid: str) -> str:
    if svc == 'steam':
        r = await steam_normalize(app, gsid)
    elif svc == 'discord':
        r = await discord_normalize(app, gsid)
    else:
        raise NotImplementedError('Not supported for this provider')

    if not r:
        raise ValueError(f'Normalization failed: Bad value {gsid} for {svc}')

    return r
