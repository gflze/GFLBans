from typing import Any, Dict, Optional, Union

from bson import ObjectId

from gflbans.internal.database.base import DBase

# Infraction
EVENT_INFRACTION_NEW = 0
EVENT_INFRACTION_REMOVE = 1
EVENT_INFRACTION_EDIT = 2
EVENT_INFRACTION_PURGE = 19
EVENT_COMMENT_NEW = 3
EVENT_COMMENT_EDIT = 4
EVENT_COMMENT_DELETE = 5
EVENT_FILE_UPLOAD = 6
EVENT_FILE_DELETE = 7
EVENT_RPC_KICK = 17

# Server
EVENT_SERVER_NEW = 8
EVENT_SERVER_EDIT = 9
EVENT_SERVER_REGENERATE_TOKEN = 18

# Group
EVENT_PERMISSIONS_GROUP_EDIT = 10
EVENT_PERMISSIONS_GROUP_ADD = 11
EVENT_PERMISSIONS_GROUP_DELETE = 12
EVENT_PERMISSIONS_ADMIN_EDIT = 13

# VPN
EVENT_VPN_NEW = 14
EVENT_VPN_DELETE = 15
EVENT_VPN_EDIT = 16


class DAuditLog(DBase):
    __collection__ = 'audit_log'

    time: int
    event_type: int
    authentication_type: int
    authenticator: ObjectId
    admin: Optional[ObjectId]

    # Store arbitrary structured data as dicts
    old_item: Optional[Union[Dict[str, Any], Any]] = None
    new_item: Optional[Union[Dict[str, Any], Any]] = None
