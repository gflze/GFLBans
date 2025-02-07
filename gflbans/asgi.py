import asyncio
import re

import uvloop
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from jinja2 import select_autoescape
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from gflbans.api import api
from gflbans.deprecation import deprecation_cleanup
from gflbans.file import file_router
from gflbans.internal.config import PRODUCTION, SECRET_KEY
from gflbans.internal.constants import GB_VERSION
from gflbans.internal.loader import gflbans_init, gflbans_unload
from gflbans.internal.log import logger
from gflbans.web import web_router

# Setup the event loop policy
from gflbans.web.context_funcs import bit_or, has_flag, render_time, tostring
from gflbans.web.pages import sctx

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


def new_app():
    # Create the FastAPI app
    app = FastAPI(redoc_url='/doc', default_response_class=ORJSONResponse)

    # Add our middleware
    app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, session_cookie='gb_session', https_only=PRODUCTION)
    app.add_middleware(GZipMiddleware)

    app.include_router(web_router, prefix='')
    app.include_router(api, prefix='/api')
    app.include_router(file_router, prefix='/file')

    app.mount('/static', StaticFiles(directory='static'), name='static')

    app.add_exception_handler(Exception, handle_exception)
    app.add_exception_handler(502, handle_exception)
    app.add_exception_handler(404, handle_exception)
    app.add_exception_handler(403, handle_exception)
    app.add_exception_handler(400, handle_exception)

    @app.on_event('shutdown')
    async def unload():
        await gflbans_unload(app)

    @app.on_event('startup')
    async def init():
        await gflbans_init(app)
        app.state.templates = Jinja2Templates(directory='templates')
        app.state.templates.env.autoescape = select_autoescape(default=True, default_for_string=True)
        app.state.templates.env.globals.update(
            has_flag=has_flag, bit_or=bit_or, render_time=render_time, tostring=tostring
        )

        if SECRET_KEY == 'testing':
            logger.warning(
                "SECRET_KEY is set to 'testing'. This is fine for development purposes, but is unsuitable for"
                ' usage in production environments.'
            )

        await deprecation_cleanup(app)

    return app


accept_regex = re.compile(r'text/html', re.IGNORECASE)


async def handle_exception(request: Request, exc):
    logger.error('An exception occurred in a view.', exc_info=exc)

    status_code = getattr(exc, 'status_code', 500)
    detail = getattr(exc, 'detail', 'An unknown error occurred.')

    if (
        'Accept' in request.headers
        and accept_regex.match(request.headers['Accept'])
        and not ('user-agent' in request.headers and 'Valve/Steam' in request.headers['user-agent'])
    ):
        # Probably a web browser, return a standard error page with error details
        return request.app.state.templates.TemplateResponse(
            'pages/error.html',
            {**await sctx(request), 'code': status_code, 'detail': detail, 'GB_VERSION': GB_VERSION},
            status_code=status_code,
        )

    # API clients will receive a proper JSON error response
    return ORJSONResponse({'detail': detail}, status_code=status_code)
