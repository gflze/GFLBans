import asyncio
import io
import re
from functools import partial
from typing import Optional

import bson
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from gridfs import AsyncGridFSBucket, NoFile
from PIL import Image
from pydantic import constr
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from gflbans.api.auth import AuthInfo, check_access
from gflbans.internal.config import MONGO_DB
from gflbans.internal.constants import API_KEY, SERVER_KEY

file_router = APIRouter()

# Attachments are stored as application/octet-stream, so these are served by extension to let browsers display them
# natively. Never add types that can run script (svg, html, xml, etc) since files are served from the site's origin.
INLINE_MEDIA_TYPES = {
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'gif': 'image/gif',
    'webp': 'image/webp',
    'mp4': 'video/mp4',
    'webm': 'video/webm',
    'mov': 'video/quicktime',
    'mp3': 'audio/mpeg',
    'ogg': 'audio/ogg',
    'opus': 'audio/ogg',
    'wav': 'audio/wav',
    'm4a': 'audio/mp4',
}

# Digits are capped to stay under int()'s string conversion limit, no real file comes close to 19 digits of bytes
range_regex = re.compile(r'^bytes=(\d{0,19})-(\d{0,19})$')


def parse_range(range_header: str, length: int) -> Optional[tuple[int, int]]:
    """Returns the inclusive (start, end) byte range, or None if it can't be satisfied"""
    match = range_regex.match(range_header.strip())

    if match is None or (match.group(1) == '' and match.group(2) == ''):
        return None

    if match.group(1) == '':
        # Suffix range, the last N bytes
        suffix = int(match.group(2))

        if suffix == 0 or length == 0:
            return None

        return max(length - suffix, 0), length - 1

    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) != '' else length - 1

    if start >= length or end < start:
        return None

    return start, min(end, length - 1)


def sync_convert_image(image_bytes, target_format):
    image_bytes = io.BytesIO(image_bytes)

    img = Image.open(image_bytes)
    tgt = io.BytesIO()

    img.save(fp=tgt, format=target_format)

    return tgt.getvalue()


@file_router.get('/uploads/{gridfs_id}/{file_name}')
async def download_file(
    request: Request,
    gridfs_id: str,
    file_name: str,
    convert_webp: Optional[constr(pattern='^(png|jpg)$')] = None,
    auth: AuthInfo = Depends(check_access),
):
    client = AsyncGridFSBucket(request.app.state.db[MONGO_DB])

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

    if t == 'application/octet-stream':
        t = INLINE_MEDIA_TYPES.get(file_name.rsplit('.', 1)[-1].lower(), t)

    if convert_webp is not None:
        if t != 'image/webp':
            raise HTTPException(detail='Requested file is not a WEBP image', status_code=400)
        if fos.length > (10 * 1024 * 1024):
            raise HTTPException(detail='File is too big to be converted on demand', status_code=400)
        if auth.type != SERVER_KEY and auth.type != API_KEY:
            raise HTTPException(detail='Must be either a server or an api key to make this request', status_code=403)

        file_contents = await fos.read()
        await fos.close()

        image_data = await asyncio.get_running_loop().run_in_executor(
            request.app.state.sync_processes, partial(sync_convert_image, file_contents, convert_webp)
        )

        mt = 'image/png' if convert_webp == 'png' else 'image/jpeg'

        return Response(
            content=image_data,
            status_code=200,
            headers={'Content-Length': str(len(image_data)), 'Cache-Control': 'no-cache'},
            media_type=mt,
        )
    else:
        headers = {
            'Cache-Control': 'public, max-age=604800, immutable',
            'Accept-Ranges': 'bytes',
            'X-Content-Type-Options': 'nosniff',
        }
        status_code = 200
        start = 0
        remaining = fos.length

        # Range requests are needed for video seeking, and iOS Safari won't play video at all without them
        if 'Range' in request.headers:
            byte_range = parse_range(request.headers['Range'], fos.length)

            if byte_range is None:
                await fos.close()
                return Response(status_code=416, headers={'Content-Range': f'bytes */{fos.length}'})

            start, end = byte_range
            remaining = end - start + 1
            status_code = 206
            headers['Content-Range'] = f'bytes {start}-{end}/{fos.length}'

        headers['Content-Length'] = str(remaining)

        async def gridfs_read():
            nonlocal remaining

            try:
                await fos.seek(start)

                while remaining > 0:
                    chunk = await fos.readchunk()

                    if not chunk:
                        break

                    chunk = chunk[:remaining]
                    remaining -= len(chunk)
                    yield chunk
            finally:
                await fos.close()

        return StreamingResponse(gridfs_read(), status_code=status_code, media_type=t, headers=headers)
