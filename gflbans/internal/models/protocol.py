# This file defines both the WebSocket and HTTP API protocol
from datetime import datetime
from typing import Optional, List, Union, Dict

from fastapi import Depends, Query
from pydantic import BaseModel, conint, PositiveInt, constr, validator, root_validator, Field, IPvAnyAddress


# Infraction related API calls
from gflbans.internal.config import MAX_UPLOAD_SIZE
from gflbans.internal.flags import valid_types_regex
from gflbans.internal.models.api import PlayerObjNoIpOptional, PositiveIntIncl0, Infraction, Initiator, \
    CInfractionSummary, \
    PlayerObjNoIp, InfractionTieringPolicyTier, PlayerObjSimple, Signature, AdminInfo, Server, ServerInternal, Group, \
    AdminMinimal, VPNInfo, InfractionDay, PlayerObjIPOptional, RawSignature


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
    xql_string: constr(min_length=1, max_length=256)
    admin: Optional[Initiator]  # Omit -> SYSTEM, None -> Guest User (can't see IPs)
    strict_xql: bool = False

    # Cursor control
    limit: conint(gt=0, le=50) = 50
    skip: PositiveIntIncl0 = 0


class SearchReply(BaseModel):
    results: List[Infraction]


class CheckInfractions(BaseModel):
    player: PlayerObjNoIpOptional = Depends(PlayerObjNoIpOptional)
    ip: Optional[str]
    include_other_servers: bool = True


class CheckInfractionsReply(BaseModel):
    voice_block: Optional[CInfractionSummary]
    chat_block: Optional[CInfractionSummary]
    ban: Optional[CInfractionSummary]
    admin_chat_block: Optional[CInfractionSummary]
    call_admin_block: Optional[CInfractionSummary]


class InfractionStatisticsReply(BaseModel):
    voice_block_count: PositiveIntIncl0
    text_block_count: PositiveIntIncl0
    ban_count: PositiveIntIncl0
    admin_chat_block_count: PositiveIntIncl0
    call_admin_block_count: PositiveIntIncl0
    warnings_count: PositiveIntIncl0


# class InfractionTieringPolicyTier(BaseModel):
#    punishments: List[constr(regex=valid_types_regex)]
#    duration: Optional[conint(gt=0)]
#    dec_online: bool = False

class RegisterInfractionTieringPolicy(BaseModel):
    name: str
    server: Optional[str]
    include_other_servers: bool = True
    tier_ttl: int  # How long an infraction counts for tiering purposes
    default_reason: constr(min_length=1, max_length=280)
    tiers: List[InfractionTieringPolicyTier]


class RegisterInfractionTieringPolicyReply(BaseModel):
    policy_id: str


class CreateInfraction(BaseModel):
    created: Optional[PositiveInt]
    duration: Optional[PositiveInt]
    player: PlayerObjSimple
    admin: Optional[Initiator]
    reason: constr(min_length=1, max_length=280)
    punishments: List[constr(regex=valid_types_regex)]
    scope: constr(regex=r'^(server|global|community)$')
    session: bool = False
    dec_online_only: bool = False
    do_full_infraction: bool = False  # Get user data / vpn check before replying to the request
    server: Optional[str]  # Override the server
    allow_normalize = False  # Attempt to convert steamid32 to steamid64, etc
    import_mode = False  # skip check of admin perms

    @root_validator(pre=True)
    def check_conflicts(cls, values):
        if 'dec_online_only' in values and values['dec_online_only'] and 'ban' in values['punishments']:
            raise ValueError('Cannot have a ban that only decreases when the player is online')

        if 'ban' in values['punishments'] and 'session' in values and values['session']:
            raise ValueError('Session bans do not make sense!')

        return values


class CreateInfractionReply(BaseModel):
    infraction: Infraction


class CreateInfractionUsingPolicy(BaseModel):
    player: PlayerObjSimple
    admin: Optional[Initiator]
    reason: Optional[constr(min_length=1, max_length=280)]
    scope: constr(regex=r'^(server|global|community)$')
    policy_id: str
    consider_other_policies: List[str] = []
    server: Optional[str]  # Override the server
    do_full_infraction = False
    allow_normalize = False  # Attempt to convert steamid32 to steamid64, etc


class UnlinkInfractionTieringPolicy(BaseModel):
    policy_id: str


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

    time_left: Optional[PositiveIntIncl0]  # Sets DEC_ONLINE_ONLY and uses this time in seconds as the initial count

    # Auto tiering
    policy_id: Union[str, None, bool]  # give False to remove, string to set

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
    scope: Optional[constr(regex=r'^(server|global|community)$')]
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
    operating_system: str
    mod: str
    map: str
    locked: bool = False
    include_other_servers: bool = True


class HeartbeatChange(BaseModel):
    player: PlayerObjNoIp
    check: CheckInfractionsReply


class RunSignatures(BaseModel):
    player: PlayerObjNoIp
    player_ip: str
    signatures: List[RawSignature]
    include_other_servers: bool = True
    make_permanent_for_evasion: bool = False


class RunSignaturesReply(BaseModel):
    check: Optional[CheckInfractionsReply]
    num_alts: int
    cloud_refused: bool = False


class GetAltsOfUser(BaseModel):
    player: PlayerObjNoIp
    signatures: List[Signature]


class GetAltsOfUserReply(BaseModel):
    alts: List[PlayerObjNoIp]


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
    friendly_name: constr(min_length=1, max_length=32)
    allow_unknown: bool = False
    discord_webhook: Optional[str]
    infract_webhook: Optional[str]
    discord_staff_tag: Optional[str]

    @root_validator(pre=True)
    def check_discord(cls, values):
        if ('discord_webhook' in values and 'discord_staff_tag' not in values) or ('discord_staff_tag' in values and 'discord_webhook' not in values):
            raise ValueError('Must give either both discord_webhook and discord_staff_tag or neither')

        return values


class AddServerReply(BaseModel):
    server: ServerInternal
    server_secret_key: str


class EditServer(BaseModel):
    ip: IPvAnyAddress
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


# Group APIs


class SetGroupPerms(BaseModel):
    permissions: PositiveIntIncl0


class SetGroupPermsReply(BaseModel):
    success: bool


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
    active_infractions: int
    total_servers: int
    online_players: int

    # Specific types, excluding admin chat / call admin bc those are kinda boring
    total_bans: int
    total_chat_blocks: int
    total_voice_blocks: int
    total_warnings: int

    # History
    history: Dict[str, InfractionDay]
