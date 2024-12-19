import asyncio
from datetime import datetime
from typing import List, Optional, Union

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic.types import constr

from gflbans.internal.database.base import DBase
from gflbans.internal.models.api import PlayerObjNoIp
from gflbans.internal.models.protocol import CheckInfractionsReply, RPCKick, RPCPlayerUpdated


class DRPCEventBase(DBase):
    __collection__ = 'rpc'

    time: datetime
    target: Optional[ObjectId]  # Omit for broadcast
    acknowledged_by: List[ObjectId] = []  # All servers that have ack'd this. Broadcast only

    @classmethod
    async def poll(cls, db_ref: AsyncIOMotorDatabase, server: ObjectId, limit=10, ack_on_read=False):
        m_cur = db_ref[cls.__collection__].find({'target': server})
        m_cur.limit(limit)

        devs = []

        async for doc in m_cur:
            if ack_on_read:
                await db_ref[cls.__collection__].delete_one({'_id': doc['_id']})
            devs.append(class_dict[doc['event']](**doc))

        if len(devs) < limit:
            # pull some broadcasts now
            m_cur = db_ref[cls.__collection__].find({'target': None, 'acknowledged_by': {'$ne': server}})
            m_cur.limit(limit - len(devs))

            async for doc in m_cur:
                dev = class_dict[doc['event']](**doc)
                devs.append(dev)

                if ack_on_read:
                    await dev.append_to_array_field(db_ref, 'acknowledged_by', server)

        return devs


class DRPCPlayerUpdated(DRPCEventBase):
    event: str = 'player_updated'

    target_type: constr(regex=r'^(player|ip)$')
    target_payload: Union[PlayerObjNoIp, str]

    local: CheckInfractionsReply
    glob: CheckInfractionsReply

    def as_api(self):
        return RPCPlayerUpdated(
            event_id=str(self.id),
            time=self.time,
            event=self.event,
            target_type=self.target_type,
            target=self.target_payload,
            local=self.local,
            glob=self.glob,
        )


class DRPCKickPlayer(DRPCEventBase):
    event: str = 'player_kick'
    target_player: PlayerObjNoIp

    def as_api(self):
        return RPCKick(target_player=self.target_player, event=self.event, event_id=str(self.id), time=self.time)


# Given the ID of an RPC event, block until a game server acknowledges it
# This can theoretically block for a very long time, so it's best to make use of asyncio timeouts
async def add_ack_concern(db, rpc_event: ObjectId):
    while True:
        ev = await DRPCEventBase.from_id(db, rpc_event)

        if ev is None or ev.acknowledged_by:
            return True  # either the event never existed, is expired, or it was already acknowledged

        await asyncio.sleep(0.5)


class_dict = {'player_updated': DRPCPlayerUpdated, 'player_kick': DRPCKickPlayer}
