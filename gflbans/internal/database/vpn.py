from typing import ClassVar

from netaddr import IPAddress, IPNetwork
from pymongo.asynchronous.database import AsyncDatabase

from gflbans.internal.database.base import DBase


class DVPN(DBase):
    __collection__: ClassVar[str] = 'vpns'
    is_asn: bool
    is_dubious: bool = False  # May be a VPN, but is prone to false positives

    payload: str  # ASN if is_asn is true, CIDR otherwise
    comment: str = 'NO COMMENT'
    added_on: float  # UNIX; legacy documents store fractional timestamps

    @classmethod
    async def find_cidr_rule(cls, db_ref: AsyncDatabase, ip: IPAddress):
        async for doc in db_ref[cls.__collection__].find({'is_asn': False}):
            a = cls.load_document(doc)

            if ip in IPNetwork(a.payload):
                return a

        return None
