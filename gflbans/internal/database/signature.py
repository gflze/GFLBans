from contextlib import suppress
from hashlib import sha256
from typing import Tuple

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from gflbans.internal.database.base import DBase
from gflbans.internal.models.api import PlayerObjNoIp


class DSignature(DBase):
    __collection__ = 'signatures'
    signature: str
    mod: str
    user: PlayerObjNoIp

    @classmethod
    async def find_all_of_signature(cls, db_ref: AsyncIOMotorDatabase, signature: Tuple[str, str]):
        async for doc in db_ref[cls.__collection__].find({'signature': signature[1], 'mod': signature[0]}):
            yield cls.load_document(doc)

    @classmethod
    async def find_all_signatures_of_users(cls, db_ref: AsyncIOMotorDatabase, gs_service: str, gs_id: str):
        async for doc in db_ref[cls.__collection__].find({'user.gs_service': gs_service, 'user.gs_id': gs_id}):
            yield cls.load_document(doc)

    @classmethod
    async def save_signature(cls, db_ref: AsyncIOMotorDatabase, user: PlayerObjNoIp, signature: Tuple[str, str]):
        with suppress(DuplicateKeyError):
            a = await db_ref[cls.__collection__].insert_one(
                cls(signature=sha256(signature[1].encode('utf-8')).hexdigest(), mod=signature[0], user=user).dict(
                    exclude_none=True, exclude_unset=True, by_alias=True
                )
            )

            assert a.acknowledged

            return a.inserted_id
