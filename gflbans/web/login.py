import os
from datetime import datetime
from typing import Optional
import urllib.parse

from aiohttp import ClientResponseError
from dateutil.tz import UTC
from fastapi import APIRouter, HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse

from gflbans.internal.config import FORUMS_OAUTH_CLIENT_ID, HOST, MONGO_DB
from gflbans.internal.database.admin import Admin
from gflbans.internal.database.uref import UserReference
from gflbans.internal.integrations.ips import get_member_id_from_token, get_user_token

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
        except ClientResponseError:
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
    request.session['oauth_state'] = os.urandom(32).hex()
    
    if dcl_token:
        request.session['dcl_state'] = {
            'oauth_state': request.session['oauth_state'],
            'dcl_token': dcl_token
        }

    parameters ={
        'openid.ns=http://specs.openid.net/auth/2.0',
        'openid.mode=checkid_setup',
        f'openid.return_to=http://{HOST}/login/finish',
        f'openid.realm=http://{HOST}',
        'openid.identity=http://specs.openid.net/auth/2.0/identifier_select',
        'openid.claimed_id=http://specs.openid.net/auth/2.0/identifier_select'
    }

    ''' Don't think this is needed, but dont delete until login is fully done and I am sure.
    parameters = {
        'openid.ns=' + urllib.parse.quote_plus('http://specs.openid.net/auth/2.0'),
        'openid.mode=' + urllib.parse.quote_plus('checkid_setup'),
        'openid.return_to=' + urllib.parse.quote_plus(f'http://{HOST}/login/finish'),
        'openid.realm=' + urllib.parse.quote_plus(f'http://{HOST}'),
        'openid.identity=' + urllib.parse.quote_plus('http://specs.openid.net/auth/2.0/identifier_select'),
        'openid.claimed_id=' + urllib.parse.quote_plus('http://specs.openid.net/auth/2.0/identifier_select')
    }
    '''

    url_params = None
    for param in parameters:
        if url_params is None:
            url_params = param
        else:
            url_params = url_params + '&' + param

    login_url = 'https://steamcommunity.com/openid/login?' + url_params

    return RedirectResponse(url=login_url)


@login_router.get('/finish')
async def finish_login(request: Request, code: str, state: str):
    if 'oauth_state' not in request.session or request.session['oauth_state'] != state:
        raise HTTPException(status_code=403, detail='State validation failed')

    now = datetime.now(tz=UTC)

    try:
        resp = await get_user_token(request.app, code)
        mid = await get_member_id_from_token(request.app, resp['access_token'])
    except ClientResponseError:
        raise HTTPException(status_code=502, detail='An upstream server rejected your login')

    uref = UserReference(authed_as=mid, access_token=resp['access_token'], created=now, last_validated=now)

    await uref.commit(request.app.state.db[MONGO_DB])

    request.session['uref'] = str(uref.id)
    del request.session['oauth_state']

    return RedirectResponse(url='/', status_code=302)


@login_router.get('/logout')
async def sign_out(request: Request):
    if 'uref' in request.session:
        del request.session['uref']

    return RedirectResponse(url='/', status_code=302)
