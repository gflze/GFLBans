from fastapi import APIRouter, HTTPException
from starlette.requests import Request

from gflbans.internal.constants import GB_VERSION
from gflbans.internal.flags import PERMISSION_VIEW_CHAT_LOGS
from gflbans.web.pages import sctx

chatlogs_router = APIRouter()


@chatlogs_router.get('/')
async def chat_logs(request: Request):
    sc = await sctx(request)
    if sc['user'] is None or not (sc['user'].permissions & PERMISSION_VIEW_CHAT_LOGS):
        raise HTTPException(detail='You do not have permission to view this page.', status_code=403)

    return request.app.state.templates.TemplateResponse(
        'pages/chat_logs.html',
        {**sc, 'page': 'chatlogs', 'GB_VERSION': GB_VERSION},
    )
