import math

import bson
from bson import ObjectId
from fastapi import APIRouter, HTTPException
from pydantic.types import constr
from starlette.requests import Request

from gflbans.internal.config import HOST, MONGO_DB
from gflbans.internal.database.infraction import DInfraction
from gflbans.internal.flags import PERMISSION_VIEW_IP_ADDR
from gflbans.internal.search import do_infraction_search
from gflbans.web.pages import sctx

from gflbans.internal.log import logger
from gflbans.internal.errors import SearchError

infractions_router = APIRouter()


@infractions_router.get('/')
async def infractions(request: Request):
    return request.app.state.templates.TemplateResponse('pages/infractions.html',
                                                        {**await sctx(request), 'page': 'infractions'})


@infractions_router.get('/{infraction_id}/')
async def preload_infraction(request: Request, infraction_id: str, search: constr(min_length=1, max_length=256) = None):
    sc = await sctx(request)
    
    try:
        obj_id = ObjectId(infraction_id)
    except bson.errors.InvalidId:
        raise HTTPException(detail='Invalid infraction ID', status_code=400)

    dinf = await DInfraction.from_id(request.app.state.db[MONGO_DB], obj_id)

    if dinf is None:
        raise HTTPException(detail='No such infraction exists', status_code=404)

    # Determine what page dinf is on

    s_dict = {'created': {'$gt': dinf.created}}

    if search:
        incl_ip = False

        if sc['user'] is not None:
            incl_ip = sc['user'].permissions & PERMISSION_VIEW_IP_ADDR == PERMISSION_VIEW_IP_ADDR

        try:
            cq, _ = await do_infraction_search(request.app, search, include_ip=incl_ip, strict=False)
        except SearchError:
            raise HTTPException(detail='Query failed to compile or took too long to execute', status_code=400)

        s_dict = {'$and': [s_dict, cq]}

    doc_num = await request.app.state.db[MONGO_DB].infractions.count_documents(s_dict)

    # The most recent infraction will have a doc_num of 1, so to get its index, just subtract 1
    doc_pos = doc_num - 1

    # doc_pos / docs_per_page floored + 1 is the page number that the document is on
    doc_page = (doc_pos // 30) + 1


    return request.app.state.templates.TemplateResponse('pages/infractions.html',
                                                        {**sc, 'page': 'infractions',
                                                         'infraction': dinf, 'set_page': doc_page,
                                                         'GB_HOST': HOST})
