from fastapi import APIRouter
from starlette.requests import Request

from gflbans.web.pages import sctx

server_mgmt_router = APIRouter()

@server_mgmt_router.get('/')
async def server_mgmt_page(request: Request):
    return request.app.state.templates.TemplateResponse('pages/server_mgmt.html', {**await sctx(request), 'page': 'manage'})
