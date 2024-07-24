from datetime import datetime

from gflbans.internal.database.base import DBase


class UserReference(DBase):
    __collection__ = 'user_cache'

    authed_as: int
    access_token: str
    created: datetime
    last_validated: datetime
