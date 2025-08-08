from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, PositiveInt, conint, constr, root_validator

PositiveIntIncl0 = conint(ge=0)


# These are objects commonly used in the API, but they do not define the protocol in itself


class PlayerObjNoIp(BaseModel):
    gs_service: str
    gs_id: str


class PlayerObjNoIpOptional(BaseModel):
    gs_service: str = None
    gs_id: str = None

    @root_validator(pre=True)
    def val(cls, values):
        if 'gs_id' in values and 'gs_service' not in values:
            raise ValueError('Incomplete admin object')

        if 'gs_service' in values and 'gs_id' not in values:
            raise ValueError('Incomplete admin object')

        return values


class PlayerObjIPOptional(BaseModel):
    gs_service: str
    gs_id: str
    ip: Optional[str]

    def __hash__(self):
        if self.ip is not None:
            return hash((self.gs_id, self.gs_service, self.ip))
        else:
            return hash((self.gs_id, self.gs_service))


class PlayerObjSimple(BaseModel):
    gs_service: Optional[str]
    gs_id: Optional[str]
    ip: Optional[str]

    @root_validator(pre=True)
    def check_validity(cls, values):
        if 'gs_id' in values and 'gs_service' not in values:
            raise ValueError('Incomplete admin object')

        if 'gs_service' in values and 'gs_id' not in values:
            raise ValueError('Incomplete admin object')

        if 'ip' not in values and 'gs_id' not in values:
            raise ValueError('Either IP or gs_id/gs_service must be present')

        return values


class FileInfo(BaseModel):
    name: str
    file_id: str
    uploaded_by: Optional[int]
    created: int = 0
    private: bool = False
    rendered: Optional[str]


class PlayerObj(PlayerObjSimple):
    # Extra data not often sent
    gs_name: Optional[str]
    gs_avatar: Optional[FileInfo]


class Comment(BaseModel):
    author: Optional[PositiveIntIncl0] = None
    content: constr(min_length=1, max_length=280)
    edit_data: Optional[Dict[str, Union[int, str]]]  # admin_id, unix time
    private: bool = False
    rendered: Optional[str]
    created: int = 0


class MessageLog(BaseModel):
    user: PlayerObj
    content: constr(min_length=1, max_length=256)
    rendered: Optional[str]
    created: int


def nn_len(v):
    i = 0

    for a in v.values():
        if a is not None:
            i += 1

    return i


class Initiator(BaseModel):
    ips_id: Optional[PositiveInt]
    mongo_id: Optional[str]
    gs_admin: Optional[PlayerObjNoIp]

    class Config:
        arbitrary_types_allowed = True

    @root_validator(pre=True)
    def validate_admin(cls, values):
        if nn_len(values) > 1:
            raise ValueError('Too much information about this admin was provided')

        return values


class Infraction(BaseModel):
    id: Optional[str]
    flags: int
    comments: List[Comment]
    files: List[FileInfo] = []
    server: Optional[str]
    created: int
    expires: Optional[PositiveIntIncl0]
    player: PlayerObj
    reason: constr(min_length=1, max_length=280)
    admin: Optional[PositiveIntIncl0]

    # Removed data
    removed_on: Optional[PositiveIntIncl0]
    removed_by: Optional[PositiveIntIncl0]
    removal_reason: Optional[constr(min_length=1, max_length=280)]

    # For PLAYTIME_DURATION
    time_left: Optional[PositiveIntIncl0]
    orig_length: Optional[PositiveIntIncl0]

    # When was the last time a heartbeat caused this to be updated?
    last_heartbeat: Optional[PositiveIntIncl0]


class Server(BaseModel):
    id: str
    ip: str
    game_port: str
    enabled: bool
    friendly_name: Optional[str]
    online: bool  # True if there is data in the cache for this server
    hostname: Optional[str]  # Unset if server hasn't connected to gflbans
    os: Optional[str]  # Unset if server hasn't connected to gflbans
    player_count: Optional[PositiveIntIncl0]  # Unset if server hasn't connected to gflbans
    max_players: Optional[PositiveIntIncl0]  # Unset if server hasn't connected to gflbans
    mod: Optional[str]
    map: Optional[str]
    is_locked: bool = False

    has_discord_webhook: Optional[bool]
    has_infract_webhook: Optional[bool]
    discord_staff_tag: Optional[str]


class ServerInternal(BaseModel):
    id: str
    ip: str
    game_port: str
    enabled: bool
    friendly_name: Optional[constr(min_length=1, max_length=48)]
    allow_unknown: bool
    discord_webhook_set: bool = False
    infract_webhook_set: bool = False
    discord_staff_tag: Optional[str]


class Group(BaseModel):
    group_name: str
    group_id: PositiveIntIncl0
    permissions: PositiveIntIncl0


class AdminInfo(BaseModel):
    admin_name: Optional[str]
    admin_id: PositiveIntIncl0
    avatar_id: Optional[str]
    permissions: Optional[PositiveIntIncl0]
    groups: Optional[List[Group]]


class FetchAdminInfo(BaseModel):
    admin_name: Optional[str]
    admin_id: Optional[PositiveIntIncl0]
    permissions: Optional[PositiveIntIncl0]
    group_id: Optional[int]


class UpdateAdminInfo(BaseModel):
    admin_name: Optional[str]
    admin_id: str
    groups: List[int]


class AdminMinimal(BaseModel):
    admin_name: Optional[str]
    admin_id: PositiveIntIncl0
    avatar_id: Optional[str]


class VPNInfo(BaseModel):
    id: str
    vpn_type: constr(regex=r'^(asn|cidr)$')
    is_dubious: bool = False
    as_number: Optional[int]
    cidr: Optional[str]
    comment: Optional[constr(min_length=1, max_length=120)]


class CInfractionSummary(BaseModel):
    expiration: Optional[PositiveInt]
    reason: str
    admin_name: str


class InfractionDay(BaseModel):
    bans: int = 0
    voice_blocks: int = 0
    chat_blocks: int = 0
    admin_chat_blocks: int = 0
    call_admin_blocks: int = 0
    item_blocks: int = 0
    warnings: int = 0
    total: int = 0


class AuditLog(BaseModel):
    time: PositiveInt
    event_type: int
    authentication_type: int
    authenticator: Optional[str]
    admin: Optional[str]

    # Store arbitrary structured data as dicts
    old_item: Optional[Union[Dict[str, Any], Any]] = None
    new_item: Optional[Union[Dict[str, Any], Any]] = None
