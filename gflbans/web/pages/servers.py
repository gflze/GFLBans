from fastapi import APIRouter
from starlette.requests import Request

from gflbans.web.pages import sctx

servers_router = APIRouter()


@servers_router.get('/')
async def servers(request: Request):
    return request.app.state.templates.TemplateResponse(
        'pages/servers.html', {**await sctx(request), 'page': 'servers'}
    )
