from datetime import datetime
from typing import Dict, Optional, Union

from bson import ObjectId
from dateutil.tz import UTC
from pydantic import BaseModel, PositiveInt, conint, conlist, constr

from gflbans.internal.constants import SERVER_KEY
from gflbans.internal.database.base import DBase
from gflbans.internal.database.common import DFile, DUser
from gflbans.internal.flags import (
    INFRACTION_DEC_ONLINE_ONLY,
    INFRACTION_GLOBAL,
    INFRACTION_PERMANENT,
    INFRACTION_REMOVED,
    INFRACTION_SESSION,
    INFRACTION_VPN,
)


class DComment(BaseModel):
    ctype: int = 0  # Deprecated
    content: constr(min_length=1, max_length=280)
    author: Optional[ObjectId]
    edit_data: Optional[Dict[str, Union[datetime, ObjectId]]] = {}  # admin_id, unix time
    private: bool = False
    created: Optional[datetime]

    class Config:
        arbitrary_types_allowed = True


def _branch(f, new_cond):
    if '$or' in f:
        if '$and' in f:
            f['$and'].append({'$or': f['$or']})
            f['$and'].append(new_cond)
        else:
            f['$and'] = [{'$or': f['$or']}, new_cond]
        del f['$or']
    else:
        f['$or'] = new_cond['$or']


# At least it's not SQL
def build_query_dict(
    actor_type: int,
    actor_id: str = None,
    gs_service: Optional[str] = None,
    gs_id: Optional[str] = None,
    ip: Optional[str] = None,
    ignore_others: bool = False,
    active_only: bool = False,
    exclude_removed: bool = False,
    online_only: bool = False,
):
    f = {}

    if gs_service is not None and gs_id is not None:
        f['user.gs_service'] = gs_service
        f['user.gs_id'] = gs_id

    if ip is not None:
        f['ip'] = ip

    # Convert into an $or if all are set
    if gs_id is not None and gs_service is not None and ip is not None:
        f['$or'] = [{'ip': ip}, {'$and': [{'user.gs_service': gs_service}, {'user.gs_id': gs_id}]}]
        del f['user.gs_service']
        del f['user.gs_id']
        del f['ip']

    # Exclude other servers
    if ignore_others:
        if actor_type != SERVER_KEY:
            raise ValueError('The `ignore_others` option is only valid for servers.')

        f['server'] = ObjectId(actor_id)

    # Filter out expired bans, vpn bans (on ip only), removed bans, session
    if active_only:
        w = [
            {'expires': {'$gt': datetime.now(tz=UTC).timestamp()}},
            {
                '$and': [
                    {'flags': {'$bitsAllSet': INFRACTION_PERMANENT}},
                    {'flags': {'$bitsAllClear': INFRACTION_SESSION}},
                ]
            },
            {
                '$and': [
                    {
                        'flags': {'$bitsAllSet': INFRACTION_DEC_ONLINE_ONLY},
                    },
                    {'time_left': {'$gt': 0}},
                ]
            },
        ]

        cond2 = {'$or': w}
        _branch(f, cond2)

        vpnf = [
            {'$and': [{'flags': {'$bitsAllClear': INFRACTION_VPN}}, {'user.gs_service': None}, {'user.gs_id': None}]},
            {'$and': [{'user.gs_service': {'$ne': None}}, {'user.gs_id': {'$ne': None}}]},
        ]

        # Once again, $or might already exist
        cond2 = {'$or': vpnf}
        _branch(f, cond2)

    if active_only or exclude_removed:
        f['flags'] = {'$bitsAllClear': INFRACTION_REMOVED}

    if online_only:
        if 'flags' not in f:
            f['flags'] = {'$bitsAllSet': INFRACTION_DEC_ONLINE_ONLY}
        elif '$bitsAllSet' not in f['flags']:
            f['flags']['$bitsAllSet'] = INFRACTION_DEC_ONLINE_ONLY
        else:
            f['flags']['$bitsAllSet'] |= INFRACTION_DEC_ONLINE_ONLY

    # Filter out server only bans that do not match our server
    if actor_type == SERVER_KEY:
        cond2 = {
            '$or': [
                {'flags': {'$bitsAllSet': INFRACTION_GLOBAL}},
                {'server': ObjectId(actor_id)},
            ]
        }
        _branch(f, cond2)
    return f


class DInfraction(DBase):
    __collection__ = 'infractions'

    # General attributes
    flags: conint(ge=0) = 0
    server: Optional[ObjectId]
    created: int
    user: Optional[DUser]
    ip: Optional[str]
    admin: Optional[ObjectId]
    reason: constr(min_length=1, max_length=280)

    # Present if using regular expiration
    expires: Optional[PositiveInt]  # UNIX

    # Present if using 'time_left' style expiration
    time_left: Optional[conint(ge=0)]
    original_time: Optional[conint(ge=0)]
    last_heartbeat: Optional[conint(ge=0)]

    # Present if the infraction was removed
    ureason: Optional[constr(min_length=1, max_length=280)]
    removed: Optional[PositiveInt]  # UNIX
    remover: Optional[ObjectId]

    # Web attributes
    comments: conlist(DComment, max_items=255) = []
    files: conlist(DFile, max_items=255) = []

    # Tiering
    policy_id: Optional[ObjectId]
