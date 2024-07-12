import asyncio
import base64
import binascii
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from typing import Optional
from bson.objectid import ObjectId
import PIL
from PIL import Image
import io

from fastapi import HTTPException
from gflbans.internal.constants import COLOR_SUCCESS, COLOR_WARNING
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from dateutil.tz import UTC

from gflbans.internal import VERSION
from gflbans.internal.config import DISCORD_BOT_TOKEN, HOST, MONGO_DB
from gflbans.internal.database.common import DFile
from gflbans.internal.database.server import DServer, DCallData
from gflbans.internal.kv import get_var
from gflbans.internal.log import logger
from gflbans.internal.models.protocol import ExecuteCallAdmin, ClaimCallAdmin

STEAM_MODS = {'csgo', 'garrysmod', 'cstrike', 'css', 'rust', 'tf'}


def clickable_where_supported(ply):
    if ply.gs_service == "steam":
        return f'[Steam](https://steamcommunity.com/profiles/{ply.gs_id})'
    else:
        return ply.gs_id


def fn(srv):
    if srv.friendly_name:
        return srv.friendly_name
    else:
        return srv.ip


async def execute_webhook(app, srv: DServer, call: ExecuteCallAdmin, image: Optional[DFile] = None):
    embed_info = {
        'color': COLOR_WARNING,
        'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'footer': {
            'icon_url': f'https://{HOST}/static/images/gflbans256.png',
            'text': f'GFLBans {VERSION}'
        },
        'fields': [
            {
                'name': 'Player',
                'value': f'{call.caller_name} ({clickable_where_supported(call.caller)})',
                'inline': True
            },
            {
                'name': 'Admin',
                'value': '(Nobody yet)',
                'inline': True
            },
            {
                'name': 'Reason',
                'value': f'{call.message}'
            }
        ]
    }

    if call.report_target:
        embed_info['fields'].insert(1, {
            'name': 'Reported Player',
            'value': f'{call.report_target_name} ({clickable_where_supported(call.report_target)})',
            'inline': True
        })

    embed_info['url'] = f'http://{HOST}/api/v1/gs/calladmin/connect?server={srv.ip}%3A{srv.game_port}'

    if srv.server_info is not None:
        embed_info['title'] = srv.server_info.hostname

        if srv.server_info.mod in STEAM_MODS:
            embed_info['description'] = f'{call.caller_name} has requested an admin on {fn(srv)}. ' \
                                        f'React :mouse: or type `!claim` in-game to claim.'
        else:
            embed_info['description'] = f'{call.caller_name} has requested an admin on {fn(srv)}. ' \
                                        f'React :mouse: or type `!claim` in-game to claim.'
    else:
        embed_info['description'] = f'{call.caller_name} has requested an admin on {fn(srv)}. ' \
                                    f'React :mouse: or type `!claim` in-game to claim.'

        embed_info['title'] = fn(srv)

    if image:
        embed_info['image'] = {
            'url': f'http://{HOST}/file/uploads/{image.gridfs_file}/{image.file_name}'
        }

        embed_info['fields'].append({
            'name': 'Warning',
            'value': 'The attached image file will expire after 30 days. If the image will be needed after this point, '
                     'you should save a copy and upload it elsewhere.',
            'inline': False
        })

    bot_name, bot_avatar = await get_var(app.state.db[MONGO_DB], 'bot.name', 'GFLBans Bot'), await get_var(
        app.state.db[MONGO_DB], 'bot.avatar',
        'https://gflusercontent.gflclan.com/file/forums-prod/monthly_2020_12/android-chrome-512x512.png')

    request_json = {'content': '@here' if srv.discord_staff_tag == 'here' else f'<@&{srv.discord_staff_tag}>',
                    'username': bot_name,
                    'avatar_url': bot_avatar,
                    'allowed_mentions': {'parse': ['everyone']} if srv.discord_staff_tag == 'here' else {'roles': [srv.discord_staff_tag]},
                    'embeds': [embed_info]}

    async with app.state.aio_session.post(srv.discord_webhook + '?wait=true',
                                          headers={'User-Agent': 'gflbans (gflclan.com, 1.0)'},
                                          json=request_json) as resp:

        try:
            resp.raise_for_status()

            result = await resp.json()

            # This is the discord message id
            # in gflbans land, we call it the claim token
            # because it's needed for an admin to claim a call
            return result['id']
        except Exception as e:
            logger.error('Failed to execute webhook!', exc_info=True)
            raise HTTPException(detail='Failed to communicate with Discord', status_code=500) from e


calladmin_thread_pool = ProcessPoolExecutor(max_workers=1)


def sync_process_calladmin_image(image: bytes):
    image = Image.open(io.BytesIO(image))
    # This functionality is almost exclusively for unturned
    # so we're gonna kneecap the res here to what unturned gives us
    image = image.resize((640, 480), resample=PIL.Image.LANCZOS)

    target = io.BytesIO()

    image.save(fp=target, format='webp', quality=100)

    new_bytes = target.getvalue()

    return new_bytes


# request context only
async def prepare_calladmin_image(db_ref, image: str) -> DFile:
    try:
        decoded = base64.b64decode(image)

        converted = await asyncio.get_running_loop().run_in_executor(calladmin_thread_pool,
                                                                     sync_process_calladmin_image, decoded)

        file_id = await AsyncIOMotorGridFSBucket(database=db_ref).upload_from_stream('callimg.webp', converted,
                                                                                     metadata={
                                                                                         'dispose_created':
                                                                                             datetime.now(tz=UTC),
                                                                                         'content-type': 'image/webp'})

        return DFile(gridfs_file=str(file_id), file_name='callimg.webp')
    except binascii.Error as e:
        raise HTTPException(detail='Bad base64 encoded image file', status_code=401) from e


async def execute_claim(app, srv: DServer, claim: ClaimCallAdmin, call: DCallData):
    embed_info = {
        'color': COLOR_SUCCESS,
        'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'footer': {
            'icon_url': f'https://{HOST}/static/images/gflbans256.png',
            'text': f'GFLBans {VERSION}'
        },
        'fields': [
            {
                'name': 'Player',
                'value': f'{call.call_info.caller_name} ({clickable_where_supported(call.call_info.caller)})',
                'inline': True
            },
            {
                'name': 'Admin',
                'value': f'{claim.admin_name}',
                'inline': True
            },
            {
                'name': 'Reason',
                'value': f'{call.call_info.message}'
            }
        ]
    }

    if call.call_info.report_target:
        embed_info['fields'].insert(1, {
            'name': 'Reported Player',
            'value': f'{call.call_info.report_target_name} ({clickable_where_supported(call.call_info.report_target)})',
            'inline': True
        })

    if srv.server_info is not None:
        embed_info['title'] = srv.server_info.hostname

        if srv.server_info.mod in STEAM_MODS:
            embed_info['description'] = f'{call.call_info.caller_name} has requested an admin on {fn(srv)}. ' \
                                        f'{claim.admin_name} took the call.'
        else:
            embed_info['description'] = f'{call.call_info.caller_name} has requested an admin on {fn(srv)}. ' \
                                        f'{claim.admin_name} took the call.'
    else:
        embed_info['title'] = fn(srv)

        embed_info['description'] = f'{call.call_info.caller_name} has requested an admin on {fn(srv)}. ' \
                                    f'{claim.admin_name} took the call.'

    embed_info['url'] = f'http://{HOST}/api/v1/gs/calladmin/connect?server={srv.ip}%3A{srv.game_port}'

    async with app.state.aio_session.patch(srv.discord_webhook + f'/messages/{call.claim_token}',
                                           headers={'User-Agent': 'gflbans (gflclan.com, 1.0)'},
                                           json={'embeds': [embed_info]}) as resp:

        try:
            resp.raise_for_status()
        except Exception as e:
            logger.error('Failed to edit webhook!', exc_info=True)
            raise HTTPException(detail='Failed to communicate with Discord', status_code=500) from e


async def claim_monitor_task(app, server_id: ObjectId, msg_id: str):
    if not DISCORD_BOT_TOKEN:
        logger.warning('No discord bot token. Claim monitor is therefore unsupported!')

    logger.debug(f'starting discord msg monitor {msg_id}')

    logger.debug(f'fetching channel id from webhook')

    srv: DServer = await DServer.from_id(app.state.db[MONGO_DB], server_id)

    if not srv or not srv.discord_webhook:
        logger.error(
            f'monitor for {msg_id} is dying because there is no server {str(server_id)} exists or no call admin')
        return

    async with app.state.aio_session.get(srv.discord_webhook,
                                         headers={'User-Agent': 'gflbans (gflclan.com, 1.0)'}) as resp:
        resp.raise_for_status()

        j = await resp.json()

        channel_id = j['channel_id']

    try:
        while True:
            await asyncio.sleep(10)
            logger.debug(f'tick monitor for {msg_id}')

            srv: DServer = await DServer.from_id(app.state.db[MONGO_DB], server_id)

            if not srv or not srv.discord_webhook:
                logger.error(
                    f'monitor for {msg_id} is dying because there is no server {str(server_id)} exists or no call admin')
                return

            if not srv.call_data or srv.call_data.claim_token != msg_id:
                logger.error(f'monitor for {msg_id} is dying because call_data is unset or has a different token')
                return

            async with app.state.aio_session.get(
                    f'https://discord.com/api/v9/channels/{channel_id}/messages/{msg_id}/reactions/%F0%9F%90%AD?limit=1',
                    headers={'User-Agent': 'gflbans (gflclan.com, 1.0)',
                             'Authorization': f'Bot {DISCORD_BOT_TOKEN}'}) as resp:
                try:
                    resp.raise_for_status()
                except Exception:
                    logger.error(f'monitor for {msg_id} dying because discord communication failure', exc_info=True)
                    raise

                j = await resp.json()

                for user in j:
                    await execute_claim(app, srv,
                                        ClaimCallAdmin(admin_name=f'{user["username"]}#{user["discriminator"]}'),
                                        srv.call_data)
                    raise StopIteration
    except StopIteration:
        pass
