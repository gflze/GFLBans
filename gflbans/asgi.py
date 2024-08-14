import asyncio
import re


import uvloop
from fastapi import FastAPI
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import ORJSONResponse
from jinja2 import select_autoescape
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from gflbans.api import api
from gflbans.file import file_router
from gflbans.internal.config import SIGNING_KEY, PRODUCTION
from gflbans.internal.loader import gflbans_init, gflbans_unload
from gflbans.internal.log import logger
from gflbans.web import web_router

# Setup the event loop policy
from gflbans.web.context_funcs import has_flag, bit_or, render_time, tostring
from gflbans.web.pages import sctx

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

def new_app():
    # Create the FastAPI app
    app = FastAPI(redoc_url='/doc', default_response_class=ORJSONResponse)

    # Add our middleware
    app.add_middleware(SessionMiddleware, secret_key=SIGNING_KEY, session_cookie='gb_session', https_only=PRODUCTION)
    app.add_middleware(GZipMiddleware)

    app.include_router(web_router, prefix='')
    app.include_router(api, prefix='/api/v1')
    app.include_router(file_router, prefix='/file')

    app.mount('/static', StaticFiles(directory='static'), name='static')

    app.add_exception_handler(Exception, handle_exception)
    app.add_exception_handler(502, handle_exception)
    app.add_exception_handler(404, handle_exception)
    app.add_exception_handler(403, handle_exception)
    app.add_exception_handler(400, handle_exception)

    @app.on_event("shutdown")
    async def unload():
        await gflbans_unload(app)


    @app.on_event("startup")
    async def init():
        await gflbans_init(app)
        app.state.templates = Jinja2Templates(directory='templates')
        app.state.templates.env.autoescape = select_autoescape(default=True, default_for_string=True)
        app.state.templates.env.globals.update(has_flag=has_flag, bit_or=bit_or, render_time=render_time, tostring=tostring)

        if SIGNING_KEY == 'testing':
            logger.warning('SECRET_KEY is set to \'testing\'. This is fine for development purposes, but is unsuitable for'
                        ' usage in production environments.')

    return app


accept_regex = re.compile(r'text/html', re.IGNORECASE)


async def handle_exception(request: Request, exc):
    logger.error('An exception occurred in a view.', exc_info=exc)
    if 'Accept' in request.headers and accept_regex.match(request.headers['Accept']):
        # Probably a web browser, give it the standard error page
        status_code = 500 if not hasattr(exc, 'status_code') else exc.status_code
        return request.app.state.templates.TemplateResponse('pages/error.html', {**await sctx(request),
                                                                                 'code': status_code})

    if hasattr(exc, 'detail'):
        return await http_exception_handler(request, exc)
    return ORJSONResponse({'detail': 'Internal Server Error'}, status_code=500)
