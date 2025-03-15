# This file defines both the WebSocket and HTTP API protocol
from datetime import datetime
from typing import Dict, List, Optional, Union

from fastapi import Depends, Query
from pydantic import BaseModel, Field, IPvAnyAddress, PositiveInt, conint, constr, root_validator, validator

# Infraction related API calls
from gflbans.internal.config import MAX_UPLOAD_SIZE
from gflbans.internal.flags import valid_types_regex
from gflbans.internal.models.api import (
    AdminInfo,
    AdminMinimal,
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
    PositiveIntIncl0,
    Server,
    ServerInternal,
    VPNInfo,
)


class GetInfractions(BaseModel):
    player: PlayerObjNoIpOptional = Depends(PlayerObjNoIpOptional)
    ip: Optional[str]
    include_other_servers: bool = True
    active_only: bool = False

    # Cursor control
    limit: conint(gt=0, le=50) = 30
    skip: PositiveIntIncl0 = 0


class GetInfractionsReply(BaseModel):
    results: List[Infraction]
    total_matched: int = 0


class GetSingleInfractionReply(BaseModel):
    infraction: Infraction


class Search(BaseModel):
    search: Optional[constr(min_length=1, max_length=256)]

    created: Optional[int]
    created_comparison_mode: Optional[constr(min_length=1, max_length=3)]
    expires: Optional[int]
    expires_comparison_mode: Optional[constr(min_length=1, max_length=3)]
    time_left: Optional[int]
    time_left_comparison_mode: Optional[constr(min_length=1, max_length=3)]
    duration: Optional[int]
    duration_comparison_mode: Optional[constr(min_length=1, max_length=3)]

    gs_service: Optional[constr(min_length=1, max_length=7)]
    gs_id: Optional[constr(min_length=1, max_length=256)]
    gs_name: Optional[constr(min_length=1, max_length=30)]
    ip: Optional[constr(min_length=1, max_length=15)]
    admin_id: Optional[constr(min_length=1, max_length=256)]
    admin: Optional[constr(min_length=1, max_length=30)]
    server: Optional[constr(min_length=1, max_length=30)]
    reason: Optional[constr(min_length=1, max_length=256)]
    ureason: Optional[constr(min_length=1, max_length=256)]
    is_active: Optional[bool]
    is_expired: Optional[bool]
    is_system: Optional[bool]
    is_global: Optional[bool]
    is_permanent: Optional[bool]
    is_playtime_duration: Optional[bool]
    is_vpn: Optional[bool]
    is_web: Optional[bool]
    is_active: Optional[bool]
    is_expired: Optional[bool]
    is_removed: Optional[bool]
    is_voice: Optional[bool]
    is_text: Optional[bool]
    is_ban: Optional[bool]
    is_admin_chat: Optional[bool]
    is_call_admin: Optional[bool]
    is_item: Optional[bool]
    is_session: Optional[bool]

    # Cursor control
    limit: conint(gt=0, le=50) = 50
    skip: PositiveIntIncl0 = 0


class SearchReply(BaseModel):
    results: List[Infraction]


class CheckInfractions(BaseModel):
    player: PlayerObjNoIpOptional = Depends(PlayerObjNoIpOptional)
    ip: Optional[str]
    reason: Optional[str]
    include_other_servers: bool = True
    active_only: bool = True
    exclude_removed: bool = False
    playtime_based: bool = False
    count_only: bool = True


class RecursiveSearch(BaseModel):
    gs_service: Optional[constr(min_length=1, max_length=7)]
    gs_id: Optional[constr(min_length=1, max_length=256)]
    ip: Optional[constr(min_length=1, max_length=15)]
    depth: conint(gt=0, le=10) = 3

    # Cursor control
    limit: conint(gt=0, le=50) = 50
    skip: PositiveIntIncl0 = 0


class CheckInfractionsReply(BaseModel):
    voice_block: Optional[CInfractionSummary]
    chat_block: Optional[CInfractionSummary]
    ban: Optional[CInfractionSummary]
    admin_chat_block: Optional[CInfractionSummary]
    call_admin_block: Optional[CInfractionSummary]
    item_block: Optional[CInfractionSummary]


class InfractionStatisticsReply(BaseModel):
    voice_block_count: PositiveIntIncl0
    voice_block_longest: Optional[int]
    text_block_count: PositiveIntIncl0
    text_block_longest: Optional[int]
    ban_count: PositiveIntIncl0
    ban_longest: Optional[int]
    admin_chat_block_count: PositiveIntIncl0
    admin_chat_block_longest: Optional[int]
    call_admin_block_count: PositiveIntIncl0
    call_admin_block_longest: Optional[int]
    item_block_count: PositiveIntIncl0
    item_block_longest: Optional[int]
    warning_count: PositiveIntIncl0
    warning_longest: Optional[int]


class CreateInfraction(BaseModel):
    created: Optional[PositiveInt]
    duration: Optional[PositiveInt]
    player: PlayerObjSimple
    admin: Optional[Initiator]
    reason: constr(min_length=1, max_length=280)
    punishments: List[constr(regex=valid_types_regex)]
    scope: constr(regex=r'^(server|global)$')
    session: bool = False
    playtime_based: bool = False
    do_full_infraction: bool = False  # Get user data / vpn check before replying to the request
    server: Optional[str]  # Override the server
    allow_normalize = False  # Attempt to convert steamid to steamid64, etc
    import_mode = False  # skip check of admin perms and just use perms of api key/server

    @root_validator(pre=True)
    def check_conflicts(cls, values):
        if 'playtime_based' in values and values['playtime_based'] and 'ban' in values['punishments']:
            raise ValueError('Cannot have a ban that is based on playtime')

        if 'ban' in values['punishments'] and 'session' in values and values['session']:
            raise ValueError('Session bans do not make sense!')

        return values


class CreateInfractionReply(BaseModel):
    infraction: Infraction


class RemoveInfractionsOfPlayer(BaseModel):
    player: PlayerObjSimple
    remove_reason: constr(min_length=1, max_length=280)
    admin: Optional[Initiator]
    include_other_servers: bool = True
    restrict_types: Optional[List[constr(regex=valid_types_regex)]]


class RemoveInfractionsOfPlayerReply(BaseModel):
    num_removed: PositiveIntIncl0
    num_considered: PositiveIntIncl0
    num_not_removed: PositiveIntIncl0


class ModifyInfraction(BaseModel):
    admin: Optional[Initiator]  # The admin making the change

    # Change the author
    author: Union[Initiator, constr(regex=r'^SYSTEM$'), None]  # string SYSTEM for SYSTEM

    # Change the expiration. All of these groups are mutually exclusive
    make_session: bool = False  # If true, make this a session infraction
    make_permanent: bool = False  # If true, make this infraction not expire
    expiration: Optional[PositiveInt]  # UNIX time that the infraction expires at.
    time_left: Optional[PositiveIntIncl0]  # Sets PLAYTIME_DURATION and uses this time in seconds as the initial count

    # Misc attrs
    make_web: bool = False
    server: Optional[str]
    reason: Optional[constr(min_length=1, max_length=280)]

    # Removal related stuff.
    set_removal_state: Optional[bool]  # None -> No change, True -> removed (following fields required), False -> not
    removed_by: Optional[Initiator]
    removal_reason: Optional[constr(min_length=1, max_length=280)]

    # Other flag stuff
    punishments: Optional[List[constr(regex=valid_types_regex)]]
    scope: Optional[constr(regex=r'^(server|global)$')]
    vpn: Optional[bool]  # Set whether or not this is a VPN IP

    @root_validator(pre=True)
    def check_conflicts(cls, values):
        if 'set_removal_state' in values and values['set_removal_state']:
            if 'removal_reason' not in values:
                raise ValueError('Missing required fields for a removal')
        return values


class ModifyInfractionReply(BaseModel):
    infraction: Infraction  # The result


class AddComment(BaseModel):
    admin: Optional[Initiator]
    content: constr(min_length=1, max_length=280)
    set_private: bool = False


class EditComment(BaseModel):
    comment_index: PositiveIntIncl0  # The index of the comment in the infraction's comment list
    admin: Optional[Initiator]
    content: constr(min_length=1, max_length=280)


class DeleteComment(BaseModel):
    comment_index: PositiveIntIncl0  # The index of the comment in the infraction's comment list
    admin: Optional[Initiator]


class AddFile(BaseModel):
    file_name: str
    contents: str = Query(..., description='Base64 encoded contents', max_length=MAX_UPLOAD_SIZE)
    admin: Optional[Initiator]


class DownloadFileByIndex(BaseModel):
    infraction_id: str
    file_idx: PositiveIntIncl0


class DownloadFileReply(BaseModel):
    contents: str = Field(..., description='Base64 Encoded')  # base 64


class DeleteFile(BaseModel):
    infraction: str
    admin: Optional[Initiator]
    file_idx: PositiveIntIncl0


class DeleteFileReply(BaseModel):
    success: bool


# Misc GS API calls


class Heartbeat(BaseModel):
    hostname: constr(max_length=96)
    max_slots: int
    players: List[PlayerObjIPOptional]
    messages: Optional[List[MessageLog]]
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

    @validator('player')
    def check_validity(cls, ply):
        if ply.ip is None:
            raise ValueError('must have an ip address')
        return ply


class CheckVPNReply(BaseModel):
    is_vpn: bool
    is_cloud_gaming: bool
    is_immune: bool


class ExecuteCallAdmin(BaseModel):
    caller: PlayerObjNoIp
    caller_name: str = 'UNKNOWN PLAYER'
    include_other_servers: bool = False
    message: constr(min_length=1, max_length=120)
    image: Optional[constr(max_length=5 * 1024 * 1024)]
    cooldown: PositiveInt = 600
    report_target: Optional[PlayerObjNoIp]
    report_target_name: str = 'UNKNOWN PLAYER'


class ExecuteCallAdminReply(BaseModel):
    sent: bool
    is_banned: bool
    cooldown: Optional[PositiveIntIncl0]


class ClaimCallAdmin(BaseModel):
    admin_name: str


class ClaimCallAdminReply(BaseModel):
    success: bool
    msg: Optional[str]


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
    discord_webhook: Optional[str]
    infract_webhook: Optional[str]
    discord_staff_tag: Optional[str]

    @root_validator(pre=True)
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
    ip: Optional[IPvAnyAddress]
    game_port: Optional[conint(gt=0, le=65535)]
    enabled: Optional[bool]
    friendly_name: Optional[constr(min_length=1, max_length=32)]
    allow_unknown: Optional[bool]
    discord_webhook: Optional[str]
    infract_webhook: Optional[str]
    discord_staff_tag: Optional[str]


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
    user: Optional[PlayerObjSimple]

    # Cursor control
    limit: conint(gt=0, le=500) = 50
    skip: PositiveIntIncl0 = 0
    created_after: PositiveIntIncl0 = 0


# Group APIs


class UpdateGroup(BaseModel):
    name: str
    privileges: PositiveIntIncl0


class GetGroups(BaseModel):
    pass


class GetGroupsReply(BaseModel):
    groups: List[Group]  # groupid, permissions


# VPN APIs
class FetchWhitelist(BaseModel):
    skip: PositiveIntIncl0
    limit: conint(gt=0, le=50)


class FetchWhitelistReply(BaseModel):
    results: List[AdminMinimal]
    total_whitelist: int = 0


class SearchWhitelist(FetchWhitelist):
    xql_query: str


class AddToWhitelist(BaseModel):
    admin: Initiator


class AddToWhitelistReply(BaseModel):
    success: bool


class RemoveFromWhitelist(BaseModel):
    admin: Initiator


class RemoveFromWhitelistReply(BaseModel):
    success: bool


class AddVPN(BaseModel):
    vpn_type: constr(regex=r'^(asn|cidr)$')
    is_cloud: bool = False
    as_number: Optional[int]
    cidr: Optional[str]
    comment: constr(min_length=1, max_length=120)


class AddVPNReply(BaseModel):
    success: bool


class FetchBlocklist(BaseModel):
    skip: PositiveIntIncl0
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
    timeout: PositiveInt = None


class RPCEventBase(BaseModel):
    event_id: str
    time: datetime
    event: str


class RPCPlayerUpdated(RPCEventBase):
    target_type: constr(regex=r'^(player|ip)$')
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
    limit: Optional[conint(gt=0, le=50)]
    skip: PositiveIntIncl0 = 0
