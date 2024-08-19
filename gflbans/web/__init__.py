from fastapi import APIRouter, Depends
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import Response

from gflbans.web.csrf import csrf_prepare
from gflbans.web.login import login_router
from gflbans.web.pages.index import index_router
from gflbans.web.pages.infractions import infractions_router
from gflbans.web.pages.servers import servers_router
from gflbans.web.pages.manage import mgmt_router

web_router = APIRouter(dependencies=[Depends(csrf_prepare)])

web_router.include_router(index_router, prefix='')
web_router.include_router(servers_router, prefix='/servers')
web_router.include_router(infractions_router, prefix='/infractions')
web_router.include_router(login_router, prefix='/login')
web_router.include_router(mgmt_router, prefix='/manage')


class SetDark(BaseModel):
    enabled: bool


@web_router.get('/toggle_theme')
async def toggle_theme(request: Request):
    if 'opposite_theme' in request.session:
        request.session['opposite_theme'] = not request.session['opposite_theme']
    else:
        request.session['opposite_theme'] = True
    return Response(status_code=204)
