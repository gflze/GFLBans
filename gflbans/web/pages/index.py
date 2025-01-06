from os.path import exists

from fastapi import APIRouter
from starlette.requests import Request

from gflbans.internal.constants import GB_VERSION
from gflbans.web.pages import sctx

index_router = APIRouter()


@index_router.get('/')
async def index(request: Request):
    # If properly setup, use configured files. Otherwise use examples as fallbacks.
    page_index_info = 'index_info.html.example'
    if exists('templates/configs/index_info.html'):
        page_index_info = 'index_info.html'

    page_index_links = 'index_links.html.example'
    if exists('templates/configs/index_links.html'):
        page_index_links = 'index_links.html'

    return request.app.state.templates.TemplateResponse(
        'pages/index.html',
        {
            **await sctx(request),
            'page': 'index',
            'page_index_info': page_index_info,
            'page_index_links': page_index_links,
            'GB_VERSION': GB_VERSION,
        },
    )
