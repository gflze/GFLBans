from typing import ClassVar

from gflbans.internal.database.base import DBase


class DGroup(DBase):
    __collection__: ClassVar[str] = 'groups'

    ips_group: int
    privileges: int
    name: str
