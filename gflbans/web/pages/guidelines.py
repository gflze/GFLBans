from os.path import exists

from fastapi import APIRouter, HTTPException
from starlette.requests import Request

from gflbans.internal.flags import PERMISSION_CREATE_INFRACTION
from gflbans.web.pages import sctx
from gflbans.internal.config import DISABLE_GUIDELINES

guidelines_router = APIRouter()

@guidelines_router.get('/')
async def guidelines(request: Request):
    if DISABLE_GUIDELINES:
        raise HTTPException(detail='Page does not exist.', status_code=404)
    
    sc = await sctx(request)
    if not ('user' in sc) or not (sc['user'].permissions & PERMISSION_CREATE_INFRACTION):
        raise HTTPException(detail='You do not have permission to view this page.', status_code=403)
    
    page_guidelines = 'guidelines.html.example'
    if exists('templates/configs/guidelines.html'):
        page_guidelines = 'guidelines.html'

    return request.app.state.templates.TemplateResponse('pages/guidelines.html',
                                                            {**sc, 'page': 'guidelines', 'page_guidelines': page_guidelines})