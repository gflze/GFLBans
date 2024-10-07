from fastapi import APIRouter

from gflbans.api.group import group_router
from gflbans.api.gs import gs_router
from gflbans.api.infraction import infraction_router
from gflbans.api.map_images import map_image_router
from gflbans.api.rpc import rpc_router
from gflbans.api.server import server_router
from gflbans.api.statistics import statistics_router
from gflbans.api.api_key import api_key_router
from gflbans.api.admin import admin_router

api = APIRouter()

api.include_router(admin_router, prefix='/admin')
api.include_router(api_key_router, prefix='/apikey')
api.include_router(group_router, prefix='/group')
api.include_router(gs_router, prefix='/gs')
api.include_router(infraction_router, prefix='/infractions')
api.include_router(map_image_router, prefix='/maps')
api.include_router(rpc_router, prefix='/rpc')
api.include_router(server_router, prefix='/server')
api.include_router(statistics_router, prefix='/statistics')