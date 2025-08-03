from typing import Any, Dict, Optional, Union

from bson import ObjectId

from gflbans.internal.database.base import DBase

# Infraction
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

# VPN
EVENT_NEW_VPN = 14
EVENT_DELETE_VPN = 15
EVENT_EDIT_VPN = 16


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
