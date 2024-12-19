import asyncio
import io
from concurrent.futures.process import ProcessPoolExecutor
from functools import partial

import PIL
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from PIL import Image

from gflbans.internal.config import MONGO_DB
from gflbans.internal.log import logger

avatar_thread_pool = ProcessPoolExecutor(max_workers=1)


async def ensure_avatar_index():
    pass


# Sync code for process_avatar to avoid blocking event loop
def sync_process_avatar(image_bytes):
    try:
        image_bytes = io.BytesIO(image_bytes)

        # Resize to 96x96 and convert to webp
        image = Image.open(image_bytes)
        image = image.resize((96, 96), resample=PIL.Image.LANCZOS)

        target = io.BytesIO()

        image.save(fp=target, format='webp', quality=100)

        new_bytes = target.getvalue()

        return new_bytes
    except Exception:
        logger.error('Failed to process avatar image.', exc_info=True)
        raise


async def process_avatar(app, avatar_url) -> dict:
    result = await app.state.db[MONGO_DB].fs.files.find_one({'metadata.retrieved_from': avatar_url})

    if result is not None:
        # Create a new file from the result
        fi = {'gridfs_file': str(result['_id']), 'file_name': 'avatar.webp'}
        return fi

    # There wasn't an existing copy, so we'll download it to gridfs
    async with app.state.aio_session.get(avatar_url) as r:
        try:
            r.raise_for_status()
        except Exception:
            logger.error('Failed to download avatar image.', exc_info=True)
            raise
        image_bytes = await r.read()

    if image_bytes is None:
        raise ValueError('Got no image')

    try:
        current_loop = asyncio.get_running_loop()
    except AttributeError:
        current_loop = asyncio.get_event_loop()

    new_image = await current_loop.run_in_executor(avatar_thread_pool, partial(sync_process_avatar, image_bytes))

    file_id = await AsyncIOMotorGridFSBucket(database=app.state.db[MONGO_DB]).upload_from_stream(
        'avatar.webp', new_image, metadata={'retrieved_from': avatar_url, 'content-type': 'image/webp'}
    )

    f = {'gridfs_file': str(file_id), 'file_name': 'avatar.webp'}

    return f
