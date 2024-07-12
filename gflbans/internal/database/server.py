import json
from datetime import datetime, timedelta
from typing import Optional, List

from dateutil.tz import UTC
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import root_validator, BaseModel

from gflbans.internal.config import SERVER_CACHE_STALE_AFTER
from gflbans.internal.database.base import DBase
from gflbans.internal.database.common import DUser
from gflbans.internal.log import logger
from gflbans.internal.models.protocol import ExecuteCallAdmin


class DUserIP(DUser):
    ip: Optional[str]


class DServerInfo(BaseModel):
    last_updated: datetime
    players: List[DUserIP] = []
    slot_count: int
    hostname: str
    os: str
    mod: str
    map: str
    locked: bool = False


class DCallData(BaseModel):
    claim_token: str
    call_info: ExecuteCallAdmin

class DServer(DBase):
    __collection__ = 'servers'
    enabled: bool = True
    ip: str
    game_port: int
    friendly_name: Optional[str]
    allow_unknown: bool = False
    discord_webhook: Optional[str]
    infract_webhook: Optional[str]
    discord_staff_tag: Optional[str]
    server_key: Optional[str]
    server_key_salt: Optional[str]

    last_calladmin: int = 0
    call_data: Optional[DCallData]

    server_info: Optional[DServerInfo]

    @root_validator(pre=True)
    def check_discord(cls, values):
        if ('discord_webhook' in values and 'discord_staff_tag' not in values) or ('discord_staff_tag' in values
                                                                                   and 'discord_webhook' not in values):
            raise ValueError('Missing discord fields!')
        return values

    @classmethod
    async def find_player(cls, db_ref: AsyncIOMotorDatabase, gs_service: str, gs_id: str):
        ds = await db_ref[cls.__collection__].find_one({
            'server_info.last_updated': {'$lt': datetime.now(tz=UTC) + timedelta(seconds=SERVER_CACHE_STALE_AFTER)},
            'server_info.players.gs_service': gs_service,
            'server_info.players.gs_id': gs_id
        })

        if ds is None:
            return None

        return cls.load_document(ds)

    @classmethod
    async def from_query_ex(cls, db_ref: AsyncIOMotorDatabase, query: dict):
        logger.debug(f'DB: running query {json.dumps(query, default=lambda o: str(o))}')

        async for document in db_ref[cls.__collection__].find(query):
            logger.debug(f'DB: load {str(document["_id"])}')
            yield cls.load_document(document)
