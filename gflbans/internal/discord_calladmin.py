from datetime import datetime
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from dateutil.tz import UTC
from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from gflbans.internal.config import BRANDING, COMMUNITY_ICON, DISCORD_BOT_TOKEN, DISCORD_PUBLIC_KEY, GFLBANS_ICON, HOST
from gflbans.internal.constants import COLOR_SUCCESS, COLOR_WARNING, GB_VERSION
from gflbans.internal.database.server import DCallAdmin, DServer
from gflbans.internal.log import logger
from gflbans.internal.models.api import PlayerObjNoIp

STEAM_MODS = {'cs2', 'garrysmod'}

DISCORD_API = 'https://discord.com/api/v10'
CLAIM_BUTTON_PREFIX = 'gflbans_calladmin_claim:'

# https://discord.com/developers/docs/interactions/receiving-and-responding
INTERACTION_PING = 1
INTERACTION_MESSAGE_COMPONENT = 3
RESPONSE_PONG = 1
RESPONSE_CHANNEL_MESSAGE = 4
RESPONSE_UPDATE_MESSAGE = 7
MESSAGE_FLAG_EPHEMERAL = 1 << 6


def sanitize_discord_username(name: str) -> str:
    replacements = {
        '*': '﹡',  # U+FE61
        '_': '＿',  # U+FF3F
        '~': '〜',  # U+301C
        '|': 'ǀ',  # U+01C0
        '`': 'ˋ',  # U+02CB
        '[': '⟦',  # U+27E6
        ']': '⟧',  # U+27E7
        '(': '﹙',  # U+FE59
        ')': '﹚',  # U+FE5A
        '<': '‹',  # U+2039
        '>': '›',  # U+203A
        '#': '＃',  # U+FF03
        ':': '꞉',  # U+A789
        '@': '＠',  # U+FF20
    }
    return ''.join(replacements.get(c, c) for c in name)


def clickable_where_supported(name: str, ply: PlayerObjNoIp):
    sanitized_name = sanitize_discord_username(name)
    if ply.gs_service == 'steam':
        return f'[{sanitized_name}](https://steamcommunity.com/profiles/{ply.gs_id})'
    else:
        return f'{sanitized_name} ({ply.gs_service}/{ply.gs_id})'


def fn(srv):
    if srv.friendly_name:
        return srv.friendly_name
    else:
        return srv.ip


def _headers(bot: bool = False) -> dict:
    headers = {'User-Agent': f'{BRANDING} ({HOST}, {GB_VERSION})'}

    if bot:
        headers['Authorization'] = f'Bot {DISCORD_BOT_TOKEN}'

    return headers


def build_call_embed(srv: DServer, call: DCallAdmin) -> dict:
    info = call.call_info
    caller_name = sanitize_discord_username(info.caller_name)

    if call.claimed_by:
        admin_name = sanitize_discord_username(call.claimed_by)
        description = f'{caller_name} has requested an admin on {fn(srv)}. {admin_name} took the call.'
    elif call.channel_id:
        admin_name = '(Nobody yet)'
        description = f'{caller_name} has requested an admin on {fn(srv)}. Press **Claim** or type `!claim` in-game.'
    else:
        admin_name = '(Nobody yet)'
        description = f'{caller_name} has requested an admin on {fn(srv)}. Type `!claim` in-game to claim.'

    embed = {
        'color': COLOR_SUCCESS if call.claimed_by else COLOR_WARNING,
        'title': srv.server_info.hostname if srv.server_info is not None else fn(srv),
        'description': description,
        'url': f'http://{HOST}/api/gs/calladmin/connect?server={srv.ip}%3A{srv.game_port}',
        'timestamp': datetime.fromtimestamp(call.created, tz=UTC).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'footer': {'icon_url': GFLBANS_ICON, 'text': f'GFLBans {GB_VERSION}'},
        'fields': [
            {'name': 'Player', 'value': clickable_where_supported(info.caller_name, info.caller), 'inline': True},
            {'name': 'Admin', 'value': admin_name, 'inline': True},
            {'name': 'Reason', 'value': info.message},
        ],
    }

    if info.report_target:
        embed['fields'].insert(
            1,
            {
                'name': 'Reported Player',
                'value': clickable_where_supported(info.report_target_name, info.report_target),
                'inline': True,
            },
        )

    if srv.server_info is not None:
        embed['fields'].append({'name': 'Map', 'value': srv.server_info.map})

    return embed


def build_call_components(call: DCallAdmin) -> list:
    if call.claimed_by or not call.channel_id:
        return []

    return [
        {
            'type': 1,  # Action row
            'components': [
                {
                    'type': 2,  # Button
                    'style': 3,  # Success (green)
                    'label': 'Claim',
                    'custom_id': f'{CLAIM_BUTTON_PREFIX}{call.id}',
                }
            ],
        }
    ]


async def get_webhook_channel(app, webhook_url: str) -> str:
    async with app.state.aio_session.get(webhook_url, headers=_headers()) as resp:
        resp.raise_for_status()
        return (await resp.json())['channel_id']


async def send_call_message(app, srv: DServer, call: DCallAdmin):
    """Post a call to Discord, setting its message_id (and channel_id if it was sent with a claim button)."""
    request_json = {
        'content': '@here' if srv.discord_staff_tag == 'here' else f'<@&{srv.discord_staff_tag}>',
        'allowed_mentions': {'parse': ['everyone']}
        if srv.discord_staff_tag == 'here'
        else {'roles': [srv.discord_staff_tag]},
    }

    try:
        if DISCORD_BOT_TOKEN:
            # Interactive buttons can't be sent through a user created webhook, so the bot posts the message itself in
            # the webhook's channel, and Discord delivers button presses to the application's interactions endpoint
            call.channel_id = await get_webhook_channel(app, srv.discord_webhook)
            request_json['embeds'] = [build_call_embed(srv, call)]
            request_json['components'] = build_call_components(call)

            async with app.state.aio_session.post(
                f'{DISCORD_API}/channels/{call.channel_id}/messages', headers=_headers(bot=True), json=request_json
            ) as resp:
                resp.raise_for_status()
                call.message_id = (await resp.json())['id']
        else:
            request_json['embeds'] = [build_call_embed(srv, call)]
            request_json['username'] = BRANDING
            request_json['avatar_url'] = COMMUNITY_ICON

            async with app.state.aio_session.post(
                srv.discord_webhook + '?wait=true', headers=_headers(), json=request_json
            ) as resp:
                resp.raise_for_status()
                call.message_id = (await resp.json())['id']
    except Exception as e:
        logger.error('Failed to send call admin message!', exc_info=True)
        raise HTTPException(detail='Failed to communicate with Discord', status_code=500) from e


async def update_call_message(app, srv: DServer, call: DCallAdmin):
    request_json = {'embeds': [build_call_embed(srv, call)], 'components': build_call_components(call)}

    if call.channel_id:
        url = f'{DISCORD_API}/channels/{call.channel_id}/messages/{call.message_id}'
        headers = _headers(bot=True)
    else:
        url = f'{srv.discord_webhook}/messages/{call.message_id}'
        headers = _headers()

    async with app.state.aio_session.patch(url, headers=headers, json=request_json) as resp:
        resp.raise_for_status()


async def try_claim_call(db_ref: AsyncDatabase, call_id: ObjectId, admin_name: str) -> Optional[DCallAdmin]:
    """Atomically claim a call, returning None if it doesn't exist or was already claimed."""
    doc = await db_ref[DCallAdmin.__collection__].find_one_and_update(
        {'_id': call_id, 'claimed_by': None},
        {'$set': {'claimed_by': admin_name, 'claimed_at': datetime.now(tz=UTC).timestamp()}},
        return_document=ReturnDocument.AFTER,
    )

    return DCallAdmin.load_document(doc) if doc else None


def verify_interaction(body: bytes, signature: Optional[str], timestamp: Optional[str]) -> bool:
    if not DISCORD_PUBLIC_KEY or not signature or not timestamp:
        return False

    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(DISCORD_PUBLIC_KEY)).verify(
            bytes.fromhex(signature), timestamp.encode() + body
        )
        return True
    except InvalidSignature, ValueError:
        return False


def interaction_display_name(interaction: dict) -> str:
    # Guild interactions carry the user inside member, alongside their server nickname
    member = interaction.get('member') or {}
    user = member.get('user') or interaction.get('user') or {}

    return member.get('nick') or user.get('global_name') or user.get('username') or 'Unknown Discord User'


def _ephemeral(content: str) -> dict:
    return {'type': RESPONSE_CHANNEL_MESSAGE, 'data': {'content': content, 'flags': MESSAGE_FLAG_EPHEMERAL}}


async def handle_interaction(db_ref: AsyncDatabase, interaction: dict) -> dict:
    if interaction.get('type') == INTERACTION_PING:
        return {'type': RESPONSE_PONG}

    custom_id = (interaction.get('data') or {}).get('custom_id', '')

    if interaction.get('type') != INTERACTION_MESSAGE_COMPONENT or not custom_id.startswith(CLAIM_BUTTON_PREFIX):
        return _ephemeral('Unknown interaction.')

    try:
        call_id = ObjectId(custom_id.removeprefix(CLAIM_BUTTON_PREFIX))
    except InvalidId:
        return _ephemeral('Unknown interaction.')

    call = await try_claim_call(db_ref, call_id, interaction_display_name(interaction))

    if call is None:
        existing = await DCallAdmin.from_id(db_ref, call_id)

        if existing is None:
            return _ephemeral('This admin call no longer exists.')

        return _ephemeral(f'This admin call was already claimed by {existing.claimed_by}.')

    srv = await DServer.from_id(db_ref, call.server)

    if srv is None:
        return _ephemeral('The server for this admin call no longer exists.')

    # Respond by editing the message the button is attached to
    return {
        'type': RESPONSE_UPDATE_MESSAGE,
        'data': {'embeds': [build_call_embed(srv, call)], 'components': build_call_components(call)},
    }
