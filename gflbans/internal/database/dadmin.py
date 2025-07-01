from typing import List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from gflbans.internal.database.base import DBase
from gflbans.internal.database.common import DFile
from gflbans.internal.log import logger


class DAdmin(DBase):
    __collection__ = 'admin_cache'

    ips_user: int
    last_updated: int = 0
    groups: List[int] = []
    name: Optional[str]
    avatar: Optional[DFile]

    @classmethod
    async def from_ips_user(cls, db_ref: AsyncIOMotorDatabase, ips_user: int):
        d = await db_ref[cls.__collection__].find_one({'ips_user': ips_user})

        if d is None:
            logger.debug(f'DB: no document for ips user {ips_user}')
            return

        logger.debug(f'DB: load {str(d["_id"])}')
        return cls.load_document(d)
