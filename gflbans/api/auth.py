import re
from hashlib import sha512
from typing import Optional, Tuple

from bson import ObjectId
from fastapi import Header, HTTPException, Query, Depends
from starlette.requests import Request

from gflbans.internal.config import MONGO_DB
from gflbans.internal.constants import API_KEY, SERVER_KEY, NOT_AUTHED_USER, AUTHED_USER
from gflbans.internal.database.admin import Admin
from gflbans.internal.flags import SERVER_KEY_PERMISSIONS
from gflbans.internal.log import logger
from gflbans.internal.utils import get_real_ip
from gflbans.web.login import current_user

auth_header_regex = re.compile(r'^(?P<actorType>server|api|SERVER|API|Server|Api)[ _]'
                               r'(?P<actorId>[a-z0-9A-Z]+)[ _](?P<actorSecret>[a-z0-9A-Z]+)$')

user_session_regex = re.compile(r'^(?P<sessionId>[a-z0-9A-Z]+)_(?P<sessionSecret>[a-z0-9A-Z]+)$')


# break this out from the main api stuff so it can be used for RPC auth
async def handle_auth_header(app, authorization, real_ip='') -> Tuple[int, Optional[ObjectId], int]:
    auth_header = auth_header_regex.match(authorization).groupdict()
    actor_id = ObjectId(auth_header['actorId'])

    if auth_header['actorType'].lower() == 'api':
        api_key = await app.state.db[MONGO_DB].api_keys.find_one({'_id': actor_id})

        if api_key is None or str(
                sha512((auth_header['actorSecret'] + api_key['key_salt']).encode('utf-8')).hexdigest()).upper() != \
                api_key['key'] or real_ip not in api_key['allowed_ip_addrs']:
            logger.info(f'Rejected api key {auth_header["actorId"]} from {real_ip}')
            raise HTTPException(detail='Invalid API Key', status_code=401)

        return API_KEY, actor_id, int(api_key['privileges'])
    elif auth_header['actorType'].lower() == 'server':
        server = await app.state.db[MONGO_DB].servers.find_one({'_id': actor_id})

        if server is None or str(sha512(
                (auth_header['actorSecret'] + server['server_key_salt']).encode('utf-8')).hexdigest()).upper() != \
                server['server_key'] or (real_ip != server['ip'] and not server['allow_unknown']):
            logger.info(f'Rejected server key for {auth_header["actorId"]} from {real_ip}')
            raise HTTPException(detail='Invalid API Key', status_code=401)

        return SERVER_KEY, actor_id, SERVER_KEY_PERMISSIONS
    else:
        raise HTTPException(detail='Invalid token type', status_code=401)


async def check_access(
        request: Request,
        authorization: str =
        Header(None, regex=r'^(server|api|SERVER|API|Server|Api)( |_)[a-z0-9A-Z]+( |_)[a-z0-9A-Z]+$',
               description='Use for server or api key auth'),
        token_type: str = Query(None, description='TYPE component of auth header if headers are not available'),
        token_id: str = Query(None, description='ID component of the auth header if headers are not available'),
        token_secret: str = Query(None, description='SECRET component of the auth header if headers are not available'),
        c_user: Optional[Admin] = Depends(current_user)
) -> Tuple[int, Optional[ObjectId], int]:  # Actor type, Actor Id, permission flags
    #  The authorization header takes priority
    if authorization is not None:
        return await handle_auth_header(request.app, authorization, real_ip=get_real_ip(request))

    #  Then we try to use the tokens
    if token_type is not None and token_id is not None and token_secret is not None:
        return await handle_auth_header(request.app, f'{token_type.upper()} {token_id} {token_secret}')

    # If session is not set, just return an unauthed user
    if c_user is None:
        return NOT_AUTHED_USER, None, 0
    else:
        return AUTHED_USER, c_user.mongo_admin_id, c_user.permissions


async def csrf_protect(request: Request,
                       x_csrf_token: str = Header(None, description='The CSRF Token'),
                       auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)):
    if auth[0] != AUTHED_USER:
        return None

    if x_csrf_token is None:
        raise HTTPException(detail='X-CSRF-TOKEN header is required for this request', status_code=403)

    if 'csrf_token' not in request.session or request.session['csrf_token'] != x_csrf_token:
        raise HTTPException(detail='CSRF token validation failed', status_code=403)

    return None
