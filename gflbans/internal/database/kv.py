from gflbans.internal.database.base import DBase

class PersistentKV(DBase):
    __collection__ = 'value_store'
    key: str
    value: str
