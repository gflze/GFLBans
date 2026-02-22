import random
import re
import urllib.parse
from datetime import datetime
from typing import Optional

import aiohttp
from dateutil.tz import UTC
from fastapi import APIRouter, HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse

from gflbans.internal.config import HOST, MONGO_DB
from gflbans.internal.database.admin import Admin
from gflbans.internal.database.uref import UserReference
from gflbans.internal.flags import PERMISSION_LOGIN
from gflbans.internal.integrations.ips import get_member_id_from_token, ips_get_member_id_from_gsid
from gflbans.internal.models.api import Initiator
from gflbans.internal.pyapi_utils import load_admin_from_initiator

login_router = APIRouter()


async def current_user(request: Request) -> Optional[Admin]:
    if 'uref' not in request.session:
        return None

    uref = await UserReference.from_id(request.app.state.db[MONGO_DB], request.session['uref'])

    if uref is None:
        del request.session['uref']
        return None

    if (datetime.now(tz=UTC).replace(tzinfo=None) - uref.last_validated).total_seconds() > 600:
        try:
            mid = await get_member_id_from_token(request.app, uref.access_token)
        except aiohttp.ClientResponseError:
            del request.session['uref']
            return None

        if mid != uref.authed_as:
            del request.session['uref']
            return None

        uref.last_validated = datetime.now(tz=UTC)
        await uref.commit(request.app.state.db[MONGO_DB])

        adm = Admin(uref.authed_as)
        await adm.fetch_details(request.app)
    else:
        adm = Admin(uref.authed_as)
        await adm.fetch_details(request.app)

    return adm


@login_router.get('/')
async def start_login(request: Request, dcl_token: str = None):
    parameters = {
        'openid.ns=http://specs.openid.net/auth/2.0',
        'openid.mode=checkid_setup',
        f'openid.return_to=http://{HOST}/login/finish',
        f'openid.realm=http://{HOST}',
        'openid.identity=http://specs.openid.net/auth/2.0/identifier_select',
        'openid.claimed_id=http://specs.openid.net/auth/2.0/identifier_select',
    }

    url_params = None
    for param in parameters:
        if url_params is None:
            url_params = param
        else:
            url_params = url_params + '&' + param

    login_url = 'https://steamcommunity.com/openid/login?' + url_params

    return RedirectResponse(url=login_url)


@login_router.get('/finish')
async def finish_login(request: Request):
    response_data = urllib.parse.parse_qs(urllib.parse.urlparse(str(request.url)).query)
    suffix_strings = str(response_data['openid.signed'][0]).split(',')
    data = {}
    for suffix in suffix_strings:
        data['openid.' + suffix] = response_data['openid.' + suffix][0]

    id_regex = re.compile(r'^https?:\/\/steamcommunity.com\/openid\/id\/(7656119[0-9]{10})\/?$')
    if (
        data['openid.claimed_id'] != data['openid.identity']
        or data['openid.op_endpoint'] != 'https://steamcommunity.com/openid/login'
        or data['openid.return_to'] != f'http://{HOST}/login/finish'
        or not id_regex.match(data['openid.identity'])
    ):
        raise HTTPException(status_code=403, detail='Login rejected')
    steam_id = int(id_regex.findall(data['openid.identity'])[0])
    data['openid.sig'] = response_data['openid.sig'][0]
    data['openid.ns'] = 'http://specs.openid.net/auth/2.0'
    data['openid.mode'] = 'check_authentication'

    async with aiohttp.ClientSession() as session:
        async with session.post(
            'https://steamcommunity.com/openid/login',
            headers={'Accept-language': 'en', 'Content-Type': 'application/x-www-form-urlencoded'},
            data=aiohttp.FormData(data),
        ) as resp:
            if resp.status >= 400:
                print(f'failed to authenticate (HTTP {resp.status}): {await resp.text()}, api request:')
                print(data)
                return
            resp_lines = str(await resp.text()).split('\n')
            resp_keys = {}
            for line in resp_lines:
                pair = line.split(':')
                if len(pair) < 2:
                    continue
                if len(pair) > 2:
                    for text in pair[2:]:
                        pair[1] = pair[1] + ':' + text  # There was a colon in text (ie. 'http://')
                resp_keys[pair[0]] = pair[1]

            if (
                'ns' not in resp_keys
                or resp_keys['ns'] != 'http://specs.openid.net/auth/2.0'
                or resp_keys['is_valid'] is None
                or resp_keys['is_valid'] != 'true'
            ):
                raise HTTPException(status_code=403, detail='Login rejected')
            ips_user = ips_get_member_id_from_gsid(steam_id)

            response = await request.app.state.db[MONGO_DB]['user_cache'].find_one({'authed_as': ips_user})

            if response is None:
                # No such user already logged in. Make sure they are allowed to login
                admin_object = await load_admin_from_initiator(request.app, Initiator(ips_id=ips_user))
                if admin_object is None or not (admin_object.permissions & PERMISSION_LOGIN):
                    raise HTTPException(status_code=403, detail='Login rejected')

                # Generate a new token to save their login
                token = random.SystemRandom().randint(1, 1 << 64)
                now = datetime.now(tz=UTC)
                uref = UserReference(authed_as=ips_user, access_token=str(token), created=now, last_validated=now)

                await uref.commit(request.app.state.db[MONGO_DB])
                request.session['uref'] = str(uref.id)
            else:
                request.session['uref'] = str(response['_id'])

            return RedirectResponse(url='/', status_code=302)


@login_router.get('/logout')
async def sign_out(request: Request):
    if 'uref' in request.session:
        del request.session['uref']

    return RedirectResponse(url='/', status_code=302)
