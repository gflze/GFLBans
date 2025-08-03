import re
from hashlib import sha512
from typing import NamedTuple, Optional

from bson import ObjectId
from fastapi import Depends, Header, HTTPException, Query
from starlette.requests import Request

from gflbans.internal.config import MONGO_DB
from gflbans.internal.constants import API_KEY, AUTHED_USER, NOT_AUTHED_USER, SERVER_KEY
from gflbans.internal.database.admin import Admin
from gflbans.internal.flags import SERVER_KEY_PERMISSIONS
from gflbans.internal.log import logger
from gflbans.internal.models.api import Initiator
from gflbans.internal.pyapi_utils import get_acting
from gflbans.internal.utils import get_real_ip
from gflbans.web.login import current_user

auth_header_regex = re.compile(
    r'^(?P<actorType>server|api|SERVER|API|Server|Api)[ _]'
    r'(?P<actorId>[a-z0-9A-Z]+)[ _](?P<actorSecret>[a-z0-9A-Z]+)$'
)

user_session_regex = re.compile(r'^(?P<sessionId>[a-z0-9A-Z]+)_(?P<sessionSecret>[a-z0-9A-Z]+)$')


class AuthInfo(NamedTuple):
    type: int
    authenticator_id: Optional[ObjectId]
    permissions: int
    admin: Optional[Admin]  # Only used if type is SERVER_KEY or API_KEY


# break this out from the main api stuff so it can be used for RPC auth
async def handle_auth_header(app, authorization, real_ip='') -> AuthInfo:
    auth_header = auth_header_regex.match(authorization).groupdict()
    actor_id = ObjectId(auth_header['actorId'])

    if auth_header['actorType'].lower() == 'api':
        api_key = await app.state.db[MONGO_DB].api_keys.find_one({'_id': actor_id})

        if (
            api_key is None
            or str(sha512((auth_header['actorSecret'] + api_key['key_salt']).encode('utf-8')).hexdigest()).upper()
            != api_key['key']
            or real_ip not in api_key['allowed_ip_addrs']
        ):
            logger.info(f'Rejected api key {auth_header["actorId"]} from {real_ip}')
            raise HTTPException(detail='Invalid API Key', status_code=401)

        return AuthInfo(API_KEY, api_key['_id'], int(api_key['privileges']), None)
    elif auth_header['actorType'].lower() == 'server':
        server = await app.state.db[MONGO_DB].servers.find_one({'_id': actor_id})

        if (
            server is None
            or str(sha512((auth_header['actorSecret'] + server['server_key_salt']).encode('utf-8')).hexdigest()).upper()
            != server['server_key']
            or (real_ip != server['ip'] and not server['allow_unknown'])
        ):
            logger.info(f'Rejected server key for {auth_header["actorId"]} from {real_ip}')
            raise HTTPException(detail='Invalid API Key', status_code=401)

        return AuthInfo(SERVER_KEY, server['_id'], SERVER_KEY_PERMISSIONS, None)
    else:
        raise HTTPException(detail='Invalid token type', status_code=401)


async def check_access(
    request: Request,
    authorization: str = Header(
        None,
        regex=r'^(server|api|SERVER|API|Server|Api)( |_)[a-z0-9A-Z]+( |_)[a-z0-9A-Z]+$',
        description='Use for server or api key auth',
    ),
    token_type: str = Query(None, description='TYPE component of auth header if headers are not available'),
    token_id: str = Query(None, description='ID component of the auth header if headers are not available'),
    token_secret: str = Query(None, description='SECRET component of the auth header if headers are not available'),
    c_user: Optional[Admin] = Depends(current_user),
) -> AuthInfo:
    real_ip = get_real_ip(request)

    if authorization:
        auth = await handle_auth_header(request.app, authorization, real_ip=real_ip)
    elif token_type and token_id and token_secret:
        auth = await handle_auth_header(request.app, f'{token_type.upper()} {token_id} {token_secret}', real_ip=real_ip)
    elif c_user is not None:
        return AuthInfo(AUTHED_USER, c_user.mongo_admin_id, c_user.permissions, c_user)
    else:
        return AuthInfo(NOT_AUTHED_USER, None, 0, None)

    if auth.type in (SERVER_KEY, API_KEY):
        try:
            body = await request.json()
            raw_admin = body.get('admin')
            if isinstance(raw_admin, dict):
                validated_admin = Initiator(**raw_admin)
                acting_admin, acting_admin_id = await get_acting(
                    request, validated_admin, auth.type, auth.authenticator_id
                )
                return AuthInfo(auth.type, auth.authenticator_id, auth.permissions, acting_admin)
        except Exception as e:
            logger.debug(f'Failed to parse request body for admin field: {e}')

    return auth


async def csrf_protect(
    request: Request,
    x_csrf_token: str = Header(None, description='The CSRF Token'),
    auth: AuthInfo = Depends(check_access),
):
    if auth.type != AUTHED_USER:
        return None

    if x_csrf_token is None:
        raise HTTPException(detail='X-CSRF-TOKEN header is required for this request', status_code=403)

    if 'csrf_token' not in request.session or request.session['csrf_token'] != x_csrf_token:
        raise HTTPException(detail='CSRF token validation failed', status_code=403)

    return None
