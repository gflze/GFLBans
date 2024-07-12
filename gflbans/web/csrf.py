import os

from starlette.requests import Request


async def csrf_prepare(request: Request) -> str:
    if 'csrf_token' not in request.session:
        request.session['csrf_token'] = os.urandom(64).hex()

    return request.session['csrf_token']
