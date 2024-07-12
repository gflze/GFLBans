import asyncio
import io
from functools import partial
from typing import Optional, Tuple

import bson
from PIL import Image
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends
from gridfs import NoFile
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from pydantic import constr
from starlette.requests import Request
from starlette.responses import StreamingResponse, Response, RedirectResponse

from gflbans.api.auth import check_access
from gflbans.internal.config import MONGO_DB
from gflbans.internal.constants import SERVER_KEY, API_KEY

file_router = APIRouter()


def sync_convert_image(image_bytes, target_format):
    image_bytes = io.BytesIO(image_bytes)

    img = Image.open(image_bytes)
    tgt = io.BytesIO()

    img.save(fp=tgt, format=target_format)

    return tgt.getvalue()


@file_router.get('/uploads/{gridfs_id}/{file_name}')
async def download_file(request: Request, gridfs_id: str, file_name: str,
                        convert_webp: Optional[constr(regex='^(png|jpg)$')] = None,
                        auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)):
    client = AsyncIOMotorGridFSBucket(database=request.app.state.db[MONGO_DB])

    try:
        fid = ObjectId(gridfs_id)
    except bson.errors.InvalidId:
        raise HTTPException(detail='Invalid Object Id', status_code=400)

    try:
        fos = await client.open_download_stream(fid)
    except NoFile:
        raise HTTPException(detail='No such file', status_code=404)

    t = 'application/octet-stream'

    if hasattr(fos, 'metadata') and fos.metadata is not None and 'content-type' in fos.metadata:
        t = fos.metadata['content-type']

    if convert_webp is not None:
        if t != 'image/webp':
            raise HTTPException(detail='Requested file is not a WEBP image', status_code=400)
        if fos.length > (10 * 1024 * 1024):
            raise HTTPException(detail='File is too big to be converted on demand', status_code=400)
        if auth[0] != SERVER_KEY and auth[0] != API_KEY:
            raise HTTPException(detail='Must be either a server or an api key to make this request', status_code=403)

        file_contents = await fos.read()

        image_data = await asyncio.get_running_loop().run_in_executor(request.app.state.sync_processes,
                                                                      partial(sync_convert_image, file_contents,
                                                                              convert_webp))

        mt = 'image/png' if convert_webp == 'png' else 'image/jpeg'

        return Response(content=image_data, status_code=200, headers={
            'Content-Length': str(len(image_data)),
            'Cache-Control': 'no-cache'
        }, media_type=mt)
    else:
        async def gridfs_read():
            while fos.tell() < fos.length:
                yield await fos.readchunk()
        return StreamingResponse(gridfs_read(), media_type=t, headers={'Content-Length': str(fos.length),
                                                                       'Cache-Control':
                                                                           'public, max-age=604800, immutable'})

