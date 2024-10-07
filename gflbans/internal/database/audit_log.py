from datetime import datetime
from typing import Optional, Tuple

from bson import ObjectId

from gflbans.internal.database.base import DBase

EVENT_NEW_INFRACTION = 0
EVENT_REMOVE_INFRACTION = 1
EVENT_EDIT_INFRACTION = 2
EVENT_NEW_COMMENT = 3
EVENT_EDIT_COMMENT = 4
EVENT_DELETE_COMMENT = 5
EVENT_UPLOAD_FILE = 6
EVENT_DELETE_FILE = 7
EVENT_RPC_KICK = 8

# Server
EVENT_NEW_SERVER = 8
EVENT_EDIT_SERVER = 9

# Group
EVENT_SET_GROUP_PERMISSIONS = 10
EVENT_ADD_GROUP = 11
EVENT_DELETE_GROUP = 12
EVENT_SET_ADMIN_PERMISSIONS = 13


class DAuditLog(DBase):
    __collection__ = 'action_log'

    time: datetime
    event_type: int
    initiator: Optional[ObjectId]
    message: str
    key_pair: Tuple[int, Optional[ObjectId]]
    long_msg: Optional[str]
