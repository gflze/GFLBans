from datetime import datetime
from pydantic import PositiveInt

from gflbans.internal.database.base import DBase


class UserReference(DBase):
    __collection__ = 'user_cache'

    authed_as: PositiveInt
    access_token: str
    created: datetime
    last_validated: datetime
