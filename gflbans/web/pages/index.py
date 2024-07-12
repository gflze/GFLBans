from fastapi import APIRouter
from starlette.requests import Request

from gflbans.web.pages import sctx

index_router = APIRouter()


@index_router.get('/')
async def index(request: Request):
    return request.app.state.templates.TemplateResponse('pages/index.html', {**await sctx(request), 'page': 'index'})
