from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, PositiveInt, conint, constr, model_validator

PositiveIntIncl0 = conint(ge=0)


# These are objects commonly used in the API, but they do not define the protocol in itself


class PlayerObjNoIp(BaseModel):
    gs_service: str
    gs_id: str


class PlayerObjNoIpOptional(BaseModel):
    gs_service: Optional[str] = None
    gs_id: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
    def val(cls, values):
        if 'gs_id' in values and 'gs_service' not in values:
            raise ValueError('Incomplete admin object')

        if 'gs_service' in values and 'gs_id' not in values:
            raise ValueError('Incomplete admin object')

        return values


class PlayerObjIPOptional(BaseModel):
    gs_service: str
    gs_id: str
    ip: Optional[str] = None

    def __hash__(self):
        if self.ip is not None:
            return hash((self.gs_id, self.gs_service, self.ip))
        else:
            return hash((self.gs_id, self.gs_service))


class PlayerObjSimple(BaseModel):
    gs_service: Optional[str] = None
    gs_id: Optional[str] = None
    ip: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
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
    uploaded_by: Optional[int] = None
    created: int = 0
    private: bool = False
    rendered: Optional[str] = None


class PlayerObj(PlayerObjSimple):
    # Extra data not often sent
    gs_name: Optional[str] = None
    gs_avatar: Optional[FileInfo] = None


class Comment(BaseModel):
    author: Optional[PositiveIntIncl0] = None
    content: constr(min_length=1, max_length=280)
    edit_data: Optional[Dict[str, Union[int, str]]] = None  # admin_id, unix time
    private: bool = False
    rendered: Optional[str] = None
    created: int = 0


class MessageLog(BaseModel):
    user: PlayerObj
    content: constr(min_length=1, max_length=512)
    rendered: Optional[str] = None
    created: int
    id: Optional[str] = None


def nn_len(v):
    i = 0

    for a in v.values():
        if a is not None:
            i += 1

    return i


class Initiator(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    ips_id: Optional[PositiveInt] = None
    mongo_id: Optional[str] = None
    gs_admin: Optional[PlayerObjNoIp] = None

    @model_validator(mode='before')
    @classmethod
    def validate_admin(cls, values):
        if nn_len(values) > 1:
            raise ValueError('Too much information about this admin was provided')

        return values


class Infraction(BaseModel):
    id: Optional[str] = None
    flags: int
    comments: List[Comment]
    files: List[FileInfo] = []
    server: Optional[str] = None
    created: int
    expires: Optional[PositiveIntIncl0] = None
    player: PlayerObj
    reason: constr(min_length=1, max_length=280)
    admin: Optional[PositiveIntIncl0] = None

    # Removed data
    removed_on: Optional[PositiveIntIncl0] = None
    removed_by: Optional[PositiveIntIncl0] = None
    removal_reason: Optional[constr(min_length=1, max_length=280)] = None

    # For PLAYTIME_DURATION
    time_left: Optional[PositiveIntIncl0] = None
    orig_length: Optional[PositiveIntIncl0] = None

    # When was the last time a heartbeat caused this to be updated?
    last_heartbeat: Optional[PositiveIntIncl0] = None


class Server(BaseModel):
    id: str
    ip: str
    game_port: str
    enabled: bool
    friendly_name: Optional[str] = None
    online: bool  # True if there is data in the cache for this server
    hostname: Optional[str] = None  # Unset if server hasn't connected to gflbans
    os: Optional[str] = None  # Unset if server hasn't connected to gflbans
    player_count: Optional[PositiveIntIncl0] = None  # Unset if server hasn't connected to gflbans
    max_players: Optional[PositiveIntIncl0] = None  # Unset if server hasn't connected to gflbans
    mod: Optional[str] = None
    map: Optional[str] = None
    is_locked: bool = False

    has_discord_webhook: Optional[bool] = None
    has_infract_webhook: Optional[bool] = None
    discord_staff_tag: Optional[str] = None


class ServerInternal(BaseModel):
    id: str
    ip: str
    game_port: str
    enabled: bool
    friendly_name: Optional[constr(min_length=1, max_length=48)] = None
    allow_unknown: bool
    discord_webhook_set: bool = False
    infract_webhook_set: bool = False
    discord_staff_tag: Optional[str] = None


class Group(BaseModel):
    group_name: str
    group_id: PositiveIntIncl0
    permissions: PositiveIntIncl0


class AdminInfo(BaseModel):
    admin_name: Optional[str] = None
    admin_id: PositiveIntIncl0
    avatar_id: Optional[str] = None
    permissions: Optional[PositiveIntIncl0] = None
    groups: Optional[List[Group]] = None


class FetchAdminInfo(BaseModel):
    admin_name: Optional[str] = None
    admin_id: Optional[PositiveIntIncl0] = None
    permissions: Optional[PositiveIntIncl0] = None
    group_id: Optional[int] = None


class UpdateAdminInfo(BaseModel):
    admin_name: Optional[str] = None
    admin_id: str
    groups: List[int]


class AdminMinimal(BaseModel):
    admin_name: Optional[str] = None
    admin_id: PositiveIntIncl0
    avatar_id: Optional[str] = None


class VPNInfo(BaseModel):
    id: str
    vpn_type: constr(pattern=r'^(asn|cidr)$')
    is_dubious: bool = False
    as_number: Optional[int] = None
    cidr: Optional[str] = None
    comment: Optional[constr(min_length=1, max_length=120)] = None


class CInfractionSummary(BaseModel):
    expiration: Optional[PositiveInt] = None
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
    authenticator: Optional[str] = None
    admin: Optional[str] = None

    # Store arbitrary structured data as dicts
    old_item: Optional[Union[Dict[str, Any], Any]] = None
    new_item: Optional[Union[Dict[str, Any], Any]] = None
