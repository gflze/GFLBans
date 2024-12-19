from motor.motor_asyncio import AsyncIOMotorDatabase
from netaddr import IPAddress, IPNetwork
from pydantic import Field

from gflbans.internal.database.base import DBase


class DVPN(DBase):
    __collection__ = 'vpns'
    is_asn: bool = Field(..., alias='payload_type')
    is_cloud: bool = False

    payload: str  # ASN if is_asn is true, CIDR otherwise
    comment: str = 'NO COMMENT'
    added_on: int

    @classmethod
    async def find_cidr_rule(cls, db_ref: AsyncIOMotorDatabase, ip: IPAddress):
        async for doc in db_ref[cls.__collection__].find({'payload_type': False}):
            a = cls.load_document(doc)

            if ip in IPNetwork(a.payload):
                return a

        return None
