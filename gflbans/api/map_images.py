import asyncio

from aiohttp import ClientResponseError
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import ORJSONResponse
from gridfs import NoFile
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from starlette.requests import Request
from starlette.responses import RedirectResponse, StreamingResponse

from gflbans.api.auth import AuthInfo, check_access
from gflbans.internal.config import MONGO_DB
from gflbans.internal.flags import PERMISSION_MANAGE_MAP_ICONS
from gflbans.internal.log import logger
from gflbans.internal.map_images import conv_map_image, find_map_image

map_image_router = APIRouter()


@map_image_router.get('/{mod_name}/{map_name}')
async def get_map_image(request: Request, mod_name: str, map_name: str):
    mf = await find_map_image(request.app.state.db[MONGO_DB], mod_name, map_name)

    if mf is None:
        gt_url = f'https://image.gametracker.com/images/maps/160x120/{mod_name}/{map_name}.jpg'
        try:
            async with request.app.state.aio_session.head(gt_url) as resp:
                if resp.status < 400:
                    return RedirectResponse(status_code=307, url=gt_url)
                else:
                    return RedirectResponse(status_code=307, url='/static/images/map_icon.png')
        except ClientResponseError:
            logger.debug('Failed to check if GameTracker has the map image we wanted', exc_info=True)
            return RedirectResponse(status_code=307, url='/static/images/map_icon.png')

    client = AsyncIOMotorGridFSBucket(database=request.app.state.db[MONGO_DB])

    try:
        fos = await client.open_download_stream(mf)
    except NoFile:
        raise HTTPException(detail='No such file', status_code=404)

    async def gridfs_read():
        while fos.tell() < fos.length:
            yield await fos.readchunk()

    return StreamingResponse(
        gridfs_read(),
        media_type='image/webp',
        headers={'Content-Length': str(fos.length), 'Cache-Control': 'public, max-age=604800,' ' immutable'},
    )


async def max_map_img_size(content_length: int = Header(..., lt=(5 * 1024 * 1024))):
    return content_length


@map_image_router.post(
    '/{mod_name}/{map_name}',
    dependencies=[Depends(max_map_img_size)],
)
async def write_map_image(
    request: Request,
    mod_name: str,
    map_name: str,
    contents: UploadFile = File(...),
    auth: AuthInfo = Depends(check_access),
):
    if auth.permissions & PERMISSION_MANAGE_MAP_ICONS != PERMISSION_MANAGE_MAP_ICONS:
        raise HTTPException(status_code=403, detail='You do not have permission to do this!')

    if not contents.content_type.startswith('image'):
        raise HTTPException(detail='Must be an image!', status_code=400)

    b = await contents.read()

    converted = await asyncio.get_running_loop().run_in_executor(None, conv_map_image, b)

    gridfs_client = AsyncIOMotorGridFSBucket(database=request.app.state.db[MONGO_DB])
    file_id = await gridfs_client.upload_from_stream(
        f'{mod_name}.{map_name}.webp',
        converted,
        metadata={'map_image': True, 'mod_name': mod_name, 'map_name': map_name, 'content-type': 'image/webp'},
    )

    return ORJSONResponse({'file_id': str(file_id)}, status_code=201)
