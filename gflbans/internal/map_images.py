import io
from typing import Optional

import PIL
from bson import ObjectId
from PIL import Image

# Internal functions for managing map images used on the front end
# Find the map image in the database
from gflbans.internal.log import logger


async def find_map_image(db_ref, mod: str, map_n: str) -> Optional[ObjectId]:
    r = await db_ref.fs.files.find_one(
        {'metadata.map_image': True, 'metadata.mod_name': mod, 'metadata.map_name': map_n}
    )

    if r is not None:
        return r['_id']

    # Try the map name without the mod
    r = await db_ref.fs.files.find_one({'metadata.map_image': True, 'metadata.map_name': map_n})

    if r is not None:
        return r['_id']

    return None


# Synchronously convert the input image to webp and scale it to 160x120
def conv_map_image(b) -> bytes:
    try:
        b = io.BytesIO(b)

        img = Image.open(b).resize((160, 120), resample=PIL.Image.LANCZOS)

        buf = io.BytesIO()
        img.save(fp=buf, format='webp', quality=100)

        return buf.getvalue()
    except Exception:
        logger.error('Failed to process map image.', exc_info=True)
        raise
