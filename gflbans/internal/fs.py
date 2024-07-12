from motor.motor_asyncio import AsyncIOMotorGridFSBucket

from gflbans.internal.config import HOST, MONGO_DB
from gflbans.internal.log import logger


async def get_media_file_url(id: str, name: str, use_https=True) -> str:
    if use_https:
        proto = 'https'
    else:
        proto = 'http'

    return f'{proto}://{HOST}/media/{id}/{name}'


async def get_media_file_url_for_template(id: str, name: str) -> str:
    return f'/media/{id}/{name}'


# Takes a string name and the byte string file contents. Returns the file id
async def save_to_gridfs(app, name, contents):
    try:
        gridfs_client = AsyncIOMotorGridFSBucket(database=app.state.db[MONGO_DB])
        file_id = await gridfs_client.upload_from_stream(name, contents)
        return file_id
    except Exception:
        logger.error('Error while uploading a file to gridfs!', exc_info=True)
        raise
