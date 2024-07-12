from gflbans.internal.database.base import DBase


class DGroup(DBase):
    __collection__ = 'groups'

    ips_group: int
    privileges: int
