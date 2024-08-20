from fastapi import APIRouter, HTTPException
from starlette.requests import Request

from gflbans.internal.flags import PERMISSION_MANAGE_GROUPS_AND_ADMINS, \
                                   PERMISSION_MANAGE_SERVERS, PERMISSION_MANAGE_API_KEYS
from gflbans.web.pages import sctx

management_router = APIRouter()

@management_router.get('/')
async def default_mgmt(request: Request):
    sc = await sctx(request)
    if sc['user'] is None:
        raise HTTPException(detail='You do not have permission to view this page.', status_code=403)

    # Default management page should be one the user has access to view
    if sc['user'].permissions & PERMISSION_MANAGE_GROUPS_AND_ADMINS:
        mode = 'admin'
    elif sc['user'].permissions & PERMISSION_MANAGE_SERVERS:
        mode = 'server'
    elif sc['user'].permissions & PERMISSION_MANAGE_API_KEYS:
        mode = 'api'

    if mode is None:
        raise HTTPException(detail='You do not have permission to view this page.', status_code=403)
    else:
        return request.app.state.templates.TemplateResponse('pages/management.html',
                                                            {**sc, 'page': 'manage',
                                                             'mode': mode})
        

@management_router.get('/admin/')
async def admin_mgmt(request: Request):
    sc = await sctx(request)

    if sc['user'] is None or not (sc['user'].permissions & PERMISSION_MANAGE_GROUPS_AND_ADMINS):
        raise HTTPException(detail='You do not have permission to view this page.', status_code=403)

    return request.app.state.templates.TemplateResponse('pages/management.html',
                                                        {**sc, 'page': 'manage',
                                                         'mode': 'admin'})


@management_router.get('/group/')
async def admin_mgmt(request: Request):
    sc = await sctx(request)

    if sc['user'] is None or not (sc['user'].permissions & PERMISSION_MANAGE_GROUPS_AND_ADMINS):
        raise HTTPException(detail='You do not have permission to view this page.', status_code=403)

    return request.app.state.templates.TemplateResponse('pages/management.html',
                                                        {**sc, 'page': 'manage',
                                                         'mode': 'group'})


@management_router.get('/server/')
async def admin_mgmt(request: Request):
    sc = await sctx(request)

    if sc['user'] is None or not (sc['user'].permissions & PERMISSION_MANAGE_SERVERS):
        raise HTTPException(detail='You do not have permission to view this page.', status_code=403)

    return request.app.state.templates.TemplateResponse('pages/management.html',
                                                        {**sc, 'page': 'manage',
                                                         'mode': 'server'})


@management_router.get('/api/')
async def admin_mgmt(request: Request):
    sc = await sctx(request)

    if sc['user'] is None or not (sc['user'].permissions & PERMISSION_MANAGE_API_KEYS):
        raise HTTPException(detail='You do not have permission to view this page.', status_code=403)

    return request.app.state.templates.TemplateResponse('pages/management.html',
                                                        {**sc, 'page': 'manage',
                                                         'mode': 'api'})

