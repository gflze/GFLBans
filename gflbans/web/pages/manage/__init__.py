from fastapi import APIRouter

from gflbans.web.pages.manage.servers import server_mgmt_router

mgmt_router = APIRouter()
mgmt_router.include_router(server_mgmt_router)