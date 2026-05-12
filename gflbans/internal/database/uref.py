from datetime import datetime
from typing import ClassVar

from gflbans.internal.database.base import DBase


class UserReference(DBase):
    __collection__: ClassVar[str] = 'user_cache'

    authed_as: int
    access_token: str
    created: datetime
    last_validated: datetime
