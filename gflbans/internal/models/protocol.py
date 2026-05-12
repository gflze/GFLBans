# This file defines both the WebSocket and HTTP API protocol
from datetime import datetime
from typing import Dict, List, Optional, Union

from fastapi import Depends, Query
from pydantic import (
    BaseModel,
    Field,
    IPvAnyAddress,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveInt,
    conint,
    constr,
    field_validator,
    model_validator,
)

# Infraction related API calls
from gflbans.internal.config import MAX_UPLOAD_SIZE
from gflbans.internal.flags import valid_types_regex
from gflbans.internal.models.api import (
    AdminInfo,
    AuditLog,
    CInfractionSummary,
    FetchAdminInfo,
    Group,
    Infraction,
    InfractionDay,
    Initiator,
    MessageLog,
    PlayerObjIPOptional,
    PlayerObjNoIp,
    PlayerObjNoIpOptional,
    PlayerObjSimple,
    Server,
    ServerInternal,
    VPNInfo,
)


class GetInfractions(BaseModel):
    player: PlayerObjNoIpOptional = Depends(PlayerObjNoIpOptional)
    ip: Optional[str] = None
    include_other_servers: bool = True
    active_only: bool = False

    # Cursor control
    limit: conint(gt=0, le=50) = 30
    skip: NonNegativeInt = 0


class GetInfractionsReply(BaseModel):
    results: List[Infraction]
    total_matched: int = 0


class GetSingleInfractionReply(BaseModel):
    infraction: Infraction


class Search(BaseModel):
    search: Optional[constr(min_length=1, max_length=256)] = None

    created: Optional[int] = None
    created_comparison_mode: Optional[constr(min_length=1, max_length=3)] = None
    expires: Optional[int] = None
    expires_comparison_mode: Optional[constr(min_length=1, max_length=3)] = None
    time_left: Optional[int] = None
    time_left_comparison_mode: Optional[constr(min_length=1, max_length=3)] = None
    duration: Optional[int] = None
    duration_comparison_mode: Optional[constr(min_length=1, max_length=3)] = None

    gs_service: Optional[constr(min_length=1, max_length=7)] = None
    gs_id: Optional[constr(min_length=1, max_length=256)] = None
    gs_name: Optional[constr(min_length=1, max_length=30)] = None
    ip: Optional[constr(min_length=1, max_length=15)] = None
    admin_id: Optional[constr(min_length=1, max_length=256)] = None
    admin: Optional[constr(min_length=1, max_length=30)] = None
    server: Optional[constr(min_length=1, max_length=30)] = None
    reason: Optional[constr(min_length=1, max_length=256)] = None
    ureason: Optional[constr(min_length=1, max_length=256)] = None
    is_active: Optional[bool] = None
    is_expired: Optional[bool] = None
    is_system: Optional[bool] = None
    is_global: Optional[bool] = None
    is_permanent: Optional[bool] = None
    is_playtime_duration: Optional[bool] = None
    is_vpn: Optional[bool] = None
    is_web: Optional[bool] = None
    is_removed: Optional[bool] = None
    is_voice: Optional[bool] = None
    is_text: Optional[bool] = None
    is_ban: Optional[bool] = None
    is_admin_chat: Optional[bool] = None
    is_call_admin: Optional[bool] = None
    is_item: Optional[bool] = None
    is_session: Optional[bool] = None

    # Cursor control
    limit: conint(gt=0, le=50) = 50
    skip: NonNegativeInt = 0


class SearchReply(BaseModel):
    results: List[Infraction]


class CheckInfractions(BaseModel):
    player: PlayerObjNoIpOptional = Depends(PlayerObjNoIpOptional)
    ip: Optional[str] = None
    reason: Optional[str] = None
    include_other_servers: bool = True
    active_only: bool = True
    exclude_removed: bool = False
    playtime_based: bool = False
    count_only: bool = True


class RecursiveSearch(BaseModel):
    gs_service: Optional[constr(min_length=1, max_length=7)] = None
    gs_id: Optional[constr(min_length=1, max_length=256)] = None
    ip: Optional[constr(min_length=1, max_length=15)] = None
    depth: conint(gt=0, le=10) = 3

    # Cursor control
    limit: conint(gt=0, le=50) = 50
    skip: NonNegativeInt = 0


class CheckInfractionsReply(BaseModel):
    voice_block: Optional[CInfractionSummary] = None
    chat_block: Optional[CInfractionSummary] = None
    ban: Optional[CInfractionSummary] = None
    admin_chat_block: Optional[CInfractionSummary] = None
    call_admin_block: Optional[CInfractionSummary] = None
    item_block: Optional[CInfractionSummary] = None


class InfractionStatisticsReply(BaseModel):
    voice_block_count: NonNegativeInt
    voice_block_longest: Optional[float] = None
    text_block_count: NonNegativeInt
    text_block_longest: Optional[float] = None
    ban_count: NonNegativeInt
    ban_longest: Optional[float] = None
    admin_chat_block_count: NonNegativeInt
    admin_chat_block_longest: Optional[float] = None
    call_admin_block_count: NonNegativeInt
    call_admin_block_longest: Optional[float] = None
    item_block_count: NonNegativeInt
    item_block_longest: Optional[float] = None
    warning_count: NonNegativeInt
    warning_longest: Optional[float] = None


class CreateInfraction(BaseModel):
    created: Optional[PositiveInt] = None
    duration: Optional[PositiveInt] = None
    auto_duration: bool = False  # If True, ignores duration
    player: PlayerObjSimple
    admin: Optional[Initiator] = None
    reason: constr(min_length=1, max_length=280)
    punishments: List[constr(pattern=valid_types_regex)]
    scope: constr(pattern=r'^(server|global)$')
    session: bool = False
    playtime_based: bool = False
    do_full_infraction: bool = False  # Get user data / vpn check before replying to the request
    server: Optional[str] = None  # Override the server
    allow_normalize: bool = False  # Attempt to convert steamid to steamid64, etc
    import_mode: bool = False  # skip check of admin perms and just use perms of api key/server

    @model_validator(mode='before')
    @classmethod
    def check_conflicts(cls, values):
        if 'playtime_based' in values and values['playtime_based'] and 'ban' in values['punishments']:
            raise ValueError('Cannot have a ban that is based on playtime')

        if 'ban' in values['punishments'] and 'session' in values and values['session']:
            raise ValueError('Session bans do not make sense!')

        return values


class CreateInfractionReply(BaseModel):
    infraction: Infraction


class CreateInfractionFromChatLog(BaseModel):
    chatlog_id: str
    preset: constr(pattern=r'^(warn|text|silence)$') = 'text'
    reason: constr(min_length=1, max_length=280)
    scope: constr(pattern=r'^(server|global)$')
    duration: Optional[PositiveInt] = None
    auto_duration: bool = False
    playtime_based: bool = False
    permanent: bool = False


class RemoveInfractionsOfPlayer(BaseModel):
    player: PlayerObjSimple
    remove_reason: constr(min_length=1, max_length=280)
    admin: Optional[Initiator] = None
    include_other_servers: bool = True
    restrict_types: Optional[List[constr(pattern=valid_types_regex)]] = None


class RemoveInfractionsOfPlayerReply(BaseModel):
    num_removed: NonNegativeInt
    num_considered: NonNegativeInt
    num_not_removed: NonNegativeInt


class ModifyInfraction(BaseModel):
    admin: Optional[Initiator] = None  # The admin making the change

    # Change the author
    author: Union[Initiator, constr(pattern=r'^SYSTEM$'), None] = None  # string SYSTEM for SYSTEM

    # Change the expiration. All of these groups are mutually exclusive
    make_session: bool = False  # If true, make this a session infraction
    make_permanent: bool = False  # If true, make this infraction not expire
    expiration: Optional[PositiveInt] = None  # UNIX time that the infraction expires at.
    # Sets PLAYTIME_DURATION and uses this time in seconds as the initial count
    time_left: Optional[NonNegativeInt] = None

    # Misc attrs
    make_web: bool = False
    server: Optional[str] = None
    reason: Optional[constr(min_length=1, max_length=280)] = None

    # Removal related stuff.
    # None -> No change, True -> removed (following fields required), False -> not
    set_removal_state: Optional[bool] = None
    removed_by: Optional[Initiator] = None
    removal_reason: Optional[constr(min_length=1, max_length=280)] = None

    # Other flag stuff
    punishments: Optional[List[constr(pattern=valid_types_regex)]] = None
    scope: Optional[constr(pattern=r'^(server|global)$')] = None
    vpn: Optional[bool] = None  # Set whether or not this is a VPN IP

    @model_validator(mode='before')
    @classmethod
    def check_conflicts(cls, values):
        if 'set_removal_state' in values and values['set_removal_state']:
            if 'removal_reason' not in values:
                raise ValueError('Missing required fields for a removal')
        return values


class ModifyInfractionReply(BaseModel):
    infraction: Infraction  # The result


class AddComment(BaseModel):
    admin: Optional[Initiator] = None
    content: constr(min_length=1, max_length=280)
    set_private: bool = False


class EditComment(BaseModel):
    comment_index: NonNegativeInt  # The index of the comment in the infraction's comment list
    admin: Optional[Initiator] = None
    content: constr(min_length=1, max_length=280)


class DeleteComment(BaseModel):
    comment_index: NonNegativeInt  # The index of the comment in the infraction's comment list
    admin: Optional[Initiator] = None


class AddFile(BaseModel):
    file_name: str
    contents: str = Query(..., description='Base64 encoded contents', max_length=MAX_UPLOAD_SIZE)
    admin: Optional[Initiator] = None


class DownloadFileByIndex(BaseModel):
    infraction_id: str
    file_idx: NonNegativeInt


class DownloadFileReply(BaseModel):
    contents: str = Field(..., description='Base64 Encoded')  # base 64


class DeleteFile(BaseModel):
    infraction: str
    admin: Optional[Initiator] = None
    file_idx: NonNegativeInt


class DeleteFileReply(BaseModel):
    success: bool


# Misc GS API calls


class Heartbeat(BaseModel):
    hostname: constr(max_length=96)
    max_slots: int
    players: List[PlayerObjIPOptional]
    messages: Optional[List[MessageLog]] = None
    operating_system: str
    mod: str
    map: str
    locked: bool = False
    include_other_servers: bool = True


class HeartbeatChange(BaseModel):
    player: PlayerObjNoIp
    check: CheckInfractionsReply


class CheckVPN(BaseModel):
    player: PlayerObjSimple = Depends(PlayerObjSimple)

    @field_validator('player')
    @classmethod
    def check_validity(cls, ply):
        if ply.ip is None:
            raise ValueError('must have an ip address')
        return ply


class CheckVPNReply(BaseModel):
    is_vpn: bool
    is_dubious: bool
    is_immune: bool
    countryName: Optional[str] = None


class ExecuteCallAdmin(BaseModel):
    caller: PlayerObjNoIp
    caller_name: str = 'UNKNOWN PLAYER'
    include_other_servers: bool = False
    message: constr(min_length=1, max_length=120)
    image: Optional[constr(max_length=5 * 1024 * 1024)] = None
    cooldown: PositiveInt = 600
    report_target: Optional[PlayerObjNoIp] = None
    report_target_name: str = 'UNKNOWN PLAYER'


class ExecuteCallAdminReply(BaseModel):
    sent: bool
    is_banned: bool
    cooldown: Optional[NonNegativeFloat] = None


class ClaimCallAdmin(BaseModel):
    admin_name: str


class ClaimCallAdminReply(BaseModel):
    success: bool
    msg: Optional[str] = None


class QueryAdminInfo(BaseModel):
    admin: Initiator


class QueryAdminInfoReply(BaseModel):
    admin: AdminInfo


# Server related routes


class GetServers(BaseModel):
    only_enabled: bool = False
    timeout: PositiveInt = 30


class GetServersReply(BaseModel):
    servers: List[Server]


class GetPlayersOfServer(BaseModel):
    server_id: str
    timeout: PositiveInt = 30


class GetPlayersOfServerReply(BaseModel):
    players: List[PlayerObjNoIp]


class AddServer(BaseModel):
    ip: IPvAnyAddress
    game_port: conint(gt=0, le=65535)
    enabled: bool = False
    friendly_name: constr(min_length=1, max_length=32)
    allow_unknown: bool = False
    discord_webhook: Optional[str] = None
    infract_webhook: Optional[str] = None
    discord_staff_tag: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
    def check_discord(cls, values):
        if ('discord_webhook' in values and 'discord_staff_tag' not in values) or (
            'discord_staff_tag' in values and 'discord_webhook' not in values
        ):
            raise ValueError('Must give either both discord_webhook and discord_staff_tag or neither')

        return values


class AddServerReply(BaseModel):
    server: ServerInternal
    server_secret_key: str


class EditServer(BaseModel):
    ip: Optional[IPvAnyAddress] = None
    game_port: Optional[conint(gt=0, le=65535)] = None
    enabled: Optional[bool] = None
    friendly_name: Optional[constr(min_length=1, max_length=32)] = None
    allow_unknown: Optional[bool] = None
    discord_webhook: Optional[str] = None
    infract_webhook: Optional[str] = None
    discord_staff_tag: Optional[str] = None


class EditServerReply(BaseModel):
    server: ServerInternal


class RegenerateServerToken(BaseModel):
    server: str


class RegenerateServerTokenReply(BaseModel):
    server_secret_key: str


class DeleteServer(BaseModel):
    server: str


class DeleteServerReply(BaseModel):
    success: bool


class RequestChatLogs(BaseModel):
    user: Optional[PlayerObjSimple] = None
    search: Optional[constr(min_length=1, max_length=256)] = None  # name or steamid
    content: Optional[constr(min_length=1, max_length=256)] = None  # search by message contents
    # Only displays messages starting with ! or /
    command_mode: Optional[constr(pattern=r'^(all|only|exclude)$')] = 'all'

    # Time range filters (unix seconds). 0 means unset.
    created_after: NonNegativeInt = 0
    created_before: NonNegativeInt = 0
    # Sort newest first for chat-style paging up
    sort_desc: bool = True

    limit: conint(gt=0, le=500) = 50


# Group APIs


class UpdateGroup(BaseModel):
    name: str
    privileges: NonNegativeInt


class GetGroups(BaseModel):
    pass


class GetGroupsReply(BaseModel):
    groups: List[Group]  # groupid, permissions


# VPN APIs
class AddVPN(BaseModel):
    vpn_type: constr(pattern=r'^(asn|cidr)$')
    is_dubious: bool = False
    as_number: Optional[int] = None
    cidr: Optional[str] = None
    comment: constr(min_length=1, max_length=120)


class AddVPNReply(BaseModel):
    success: bool


class PatchVPN(BaseModel):
    id: str
    vpn_type: Optional[constr(pattern=r'^(asn|cidr)$')] = None
    is_dubious: Optional[bool] = None
    as_number: Optional[int] = None
    cidr: Optional[str] = None
    comment: Optional[constr(min_length=1, max_length=120)] = None

    @model_validator(mode='before')
    @classmethod
    def check_type(cls, values):
        if ('vpn_type' in values and values['vpn_type'] == 'cidr' and 'cidr' not in values) or (
            'vpn_type' in values and values['vpn_type'] == 'asn' and 'as_number' not in values
        ):
            raise ValueError(
                'If vpn_type is being changed, the matchin identifier (cidr or as_number) must also be provided'
            )

        return values


class FetchBlocklist(BaseModel):
    skip: NonNegativeInt
    limit: conint(gt=0, le=50)
    filter: str


class FetchBlocklistReply(BaseModel):
    results: List[VPNInfo]
    total_blocks: int


class RemoveVPN(BaseModel):
    as_number_or_cidr: str


class RemoveVPNReply(BaseModel):
    success: bool


# Server to client communications, often called RPC.


class PollRPC(BaseModel):
    timeout: Optional[PositiveInt] = None


class RPCEventBase(BaseModel):
    event_id: str
    time: datetime
    event: str


class RPCPlayerUpdated(RPCEventBase):
    target_type: constr(pattern=r'^(player|ip)$')
    target: Union[PlayerObjNoIp, str]

    local: CheckInfractionsReply
    glob: CheckInfractionsReply


class RPCKick(RPCEventBase):
    target_player: PlayerObjNoIp


class RPCKickRequest(BaseModel):
    server_id: str
    player: PlayerObjNoIp


class ServerStats(BaseModel):
    # General stuff
    total_infractions: int

    # Specific types, excluding admin chat, call admin, and item blocks bc those are kinda boring
    total_bans: int
    total_chat_blocks: int
    total_voice_blocks: int
    total_admin_chat_blocks: int
    total_call_admin_blocks: int
    total_item_blocks: int
    total_warnings: int

    # History
    history: Dict[str, InfractionDay]


class GetAdmins(BaseModel):
    admin: FetchAdminInfo = Depends(FetchAdminInfo)

    # Cursor control
    limit: Optional[conint(gt=0, le=50)] = None
    skip: NonNegativeInt = 0


class GetAuditLogs(BaseModel):
    event_type: Optional[List[int]] = None
    authenticator: Optional[str] = None
    admin: Optional[str] = None

    # Cursor control
    limit: conint(gt=0, le=50) = 30
    skip: NonNegativeInt = 0


class GetAuditLogsReply(BaseModel):
    results: List[AuditLog]
    total_matched: int = 0
