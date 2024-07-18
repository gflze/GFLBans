# GFLBans API for Plugins

This document contains the necessary information to implement a basic GFLBans plugin.

The GFLBans API can be found at the `/api/v1/` route of the main instance. For example, if your instance is hosted at `bans.gflclan.com`, the api would be at `bans.gflclan.com/api/v1/`

The following sub-routes make up the API:

|Route|Description|
|-----|-----------|
|/infractions|All infraction related operations|
|/gs|Misc. routes useful to the GFLBans plugin|
|/rpc|Routes that can be used by the GFLBans plugin to receive data from GFLBans|

There are other sub-routes, but they aren't useful for the plugin.

***

## Authentication

All API requests should be authenticated using the Authorization header.

```
Authorization: SERVER SERVER_ID SERVER_KEY
```

`SERVER_ID` and `SERVER_KEY` are user supplied parameters. Make sure the user can configure them.

***

## Common structures

These structs are referenced throughout this document and are provided here to avoid repetition

```Python
class PlayerObjIPOptional:
    gs_service: str
    gs_id: str
    ip: Optional[str]

class PlayerObjNoIp(BaseModel):
    gs_service: str
    gs_id: str

class PlayerObjSimple(BaseModel):
    gs_service: str
    gs_id: str
    ip: Optional[str]

class CInfractionSummary:
    expiration: Optional[PositiveInt]  # Unix timestamp
    reason: str
    admin_name: str

# SEND ONLY ONE OF THESE FIELDS
class Initiator:
    ips_id: Optional[PositiveInt]  # Aurora: Ips id is like the number in their forum profile url
    mongo_id: Optional[str]        # Internal database id
    gs_admin: Optional[PlayerObjNoIp]

class Infraction:
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

    # For DEC_ONLINE_ONLY
    time_left: Optional[PositiveIntIncl0]
    orig_length: Optional[PositiveIntIncl0]

    # For tiering policy
    policy_id: Optional[str]

    # When was the last time a heartbeat caused this to be updated?
    last_heartbeat: Optional[PositiveIntIncl0]
```

***

## Heartbeat

The GFLBans plugin should periodically send data to GFLBans so that GFLBans can:

 - Know if the server is alive
 - Update infractions that only decrement while the player is online
 - Display information about the server in the Web UI

The heartbeat route is present at `/api/v1/gs/heartbeat` and should be POSTed with JSON data in the following format:

```Python
class Heartbeat:
    hostname: constr(max_length=96)
    max_slots: int
    players: List[PlayerObjIPOptional]
    operating_system: str
    mod: str
    map: str
    locked: bool = False
    include_other_servers: bool = True
```
|Field|Type|Description|
|---------|----|-----------|
|hostname|constr(max_length=96)|The hostname of the server. Type `hostname` in console.|
|max_slots|int|Max players of the server. Usually using GetMaxHumanPlayers() will work.|
|players|List[PlayerObjIpOptional]|Self explanatory. A json array of players that follows `PlayerObjIPOptional` class|
|operating_system|str|`Windows` or `Linux`|
|mod|str|The name of the game folder (`csgo` for CS:GO, `cstrike` for CS:S, `tf` for TF2)|
|map|str|The current map|
|locked|bool|Whether `sv_password` is set so that only people with the password can join.|
|include_other_servers|bool|If the plugin configuration wants to accept GLOBAL GFL bans|

The API will reply with a list of `HeartbeatChange` objects:

```Python
class HeartbeatChange:
    player: PlayerObjNoIp
    check: CheckInfractionsReply

class CheckInfractionsReply:
    voice_block: Optional[CInfractionSummary]
    chat_block: Optional[CInfractionSummary]
    ban: Optional[CInfractionSummary]
    admin_chat_block: Optional[CInfractionSummary]
    call_admin_block: Optional[CInfractionSummary]

class CInfractionSummary:
    expiration: Optional[PositiveInt]  # Unix timestamp
    reason: str
    admin_name: str
```

Using that information, you should update the user's local state and, if necessary, kick them.
You can omit `call_admin_blocks` from the local state since GFLBans enforces them server side.

It is recommended that a heartbeat is sent each minute, though servers can get away with doing as much as 10 minutes in between beats.

***

## RPC Events

GFLBans uses RPC events to tell the server to do things and to inform it of changes. RPC events can be retrieved by polling `/api/v1/rpc/poll` or sent as they become available by listening on Websocket `/api/v1/rpc/ws`

RPC event responses have the generic form

```python
class RPCEventBase:
    event_id: str
    time: datetime
    event: str
```

The event_id field is a unique id that GFLBans can use to identify events. The time is the time the event was created. The event is the event type.

Each event type has it's own fields.

Here are the currently implemented events:

```python
#event: player_updated
class RPCPlayerUpdated(RPCEventBase):
    target_type: constr(regex=r'^(player|ip)$')  # ip or player. If player, then target is a PlayerObjNoIp, else string
    target: Union[PlayerObjNoIp, str]

    local: CheckInfractionsReply  # See definition in the heartbeat section
    glob: CheckInfractionsReply
```

The player_updated event is sent when the server wants to push new state to the game server. You should use this information to update the user's local state and, if necessary, kick them. The `local` field should be used if the server administrator has configured the server to ignore global bans, otherwise the `glob` field should be used.

```python
#event: player_kick
class RPCKick(RPCEventBase):
    target_player: PlayerObjNoIp
```

If the player is present in-game, kick them.

***

## Checking player infractions

GFLBans will send events to the server, however, when a player first joins, you should check a player's infractions to establish their initial state.

To retrieve a player's information, send a GET request to `/api/v1/infractions/check`

The following parameters are accepted:

|Parameter|Type|Description|
|---------|----|-----------|
|gs_service|str|The service component of the player object, usually `steam`|
|gs_id|str|The id component of the player object. For steam, this is their steamid64|
|ip|str|The IP address of the player|
|include_other_servers|bool|Whether or not to accept global infractions issued on other servers. Should be configurable by the manager||

GFLBans will reply with an object like:

```python
class CheckInfractionsReply:
    voice_block: Optional[CInfractionSummary]
    chat_block: Optional[CInfractionSummary]
    ban: Optional[CInfractionSummary]
    admin_chat_block: Optional[CInfractionSummary]
    call_admin_block: Optional[CInfractionSummary]

class CInfractionSummary:
    expiration: Optional[PositiveInt]  # Unix timestamp
    reason: str
    admin_name: str
```

You should use this to reject the players connection / kick them if they are banned, or apply other restrictions.

For the sake of being user friendly, it is recommended that you inform the player of the admin that banned, muted, or gagged them and the reason for which they were punished.

It is unnecessary to take action for `call_admin_block` as that is handled by GFLBans web. Furthermore, `admin_chat_block` can be ignored if there is no admin chat function.

***

## Utilising VPN features

You can use GFLBans' built in VPN detection by sending a GET request to `/api/v1/gs/vpn` on player join. The route accepts the following parameters:

|Parameter|Type|Description|
|---------|----|-----------|
|gs_service|str|The service component of the player object, usually `steam`|
|gs_id|str|The id component of the player object. For steam, this is their steamid64|
|ip|str|The player's ip address|

GFLBans will reply with something like this

```python
class CheckVPNReply:
    is_vpn: bool
    is_cloud_gaming: bool
    is_immune: bool
```

The plugin is recommended to inform admins about a player joining with a vpn if `is_vpn` is true.

Depending on plugin configuration, the server may also kick them. If `is_immune` is set, the player should not be kicked.

The server may choose how to handle `is_cloud_gaming` depending on whether or not they want to allow or kick cloud gaming services.

***

## Calling an admin

You can utilise GFLBans' implementation of call admin by sending a POST request to `/api/v1/gs/calladmin`.

The calladmin route is rate limited to once per 10 minutes by default, but can be overridden to a server's preferred value using the cooldown parameter. Rate limiting is controlled by GFLBans.

The POST sent to GFLBans should look like this:

```python
class ExecuteCallAdmin:
    caller: PlayerObjNoIp
    caller_name: str
    include_other_servers: bool = False
    message: constr(min_length=1, max_length=120)
    cooldown: PositiveInt = 600  # seconds
    report_target: Optional[PlayerObjNoIp]
    report_target_name: Optional[str]
```

Most of the parameters should be self-explanatory. The include_other_servers parameter should be true if the server is accepting global bans, but false if the server is ignoring them. Specifying report_target will change the call admin embed into a report embed.

GFLBans will send a reply that looks like this:

```python
class ExecuteCallAdminReply:
    sent: bool
    is_banned: bool
    cooldown: Optional[PositiveIntIncl0]
```

The player should be informed if an admin was called, how much cooldown remains, and whether they are banned from using call admin.

***

## Creating an infraction using tiering policies

If you want to implement https://gflclan.com/forums/topic/68218-new-punishment-system-for-gflbans-03-beta/ (which you should), these API routes will let you do it.

The first component of this is registering an infraction template with GFLBans. This should be done before any bans would be made, probably during plugin init.

The infraction template should only be registered once. You should check to see if you have a policy_id for the offense code before trying again.

You can register the template by POSTing to `/api/v1/infractions/register_policy`

The following data should be posted:

```python
class RegisterInfractionTieringPolicy:
    name: str
    server: Optional[str]
    include_other_servers: bool = True
    tier_ttl: int  # How long an infraction counts for tiering purposes
    default_reason: constr(min_length=1, max_length=280)
    tiers: List[InfractionTieringPolicyTier]

class InfractionTieringPolicyTier:
    punishments: List[constr(regex=valid_types_regex)]
    duration: Optional[conint(gt=0)]
    dec_online: bool = False
```

`name` is just a user friendly name of the policy.
`server` is the SERVER_ID (same one as you stick in the auth header)
`include_other_servers` is whether or not the server is accepting globals
`punishments` should be one of `voice_block`, `chat_block`, `ban`, `admin_chat_block`, or `call_admin_block`
`duration` is the length of the infraction in seconds. OMIT entirely for permanent.
`dec_online` is whether or not the infraction only decreases while the player is connected to the server. Doesn't work with `ban`

GFLBans will reply with

```python
class RegisterInfractionTieringPolicyReply:
    policy_id: str
```

policy_id is a unique id of the newly created tiering policy that GFLBans uses to identify the saved configuration.

You should save this in local storage (SQLite, config file, etc) and associate it with the offense code as laid out in the above forum post.

When you'd actually like to ban a player, you can POST to `/api/v1/infractions/using_policy` with the following:

```python
class CreateInfractionUsingPolicy(BaseModel):
    player: PlayerObjSimple
    admin: Optional[Initiator]
    reason: Optional[constr(min_length=1, max_length=280)]
    scope: constr(regex=r'^(server|global|community)$')  # the plugin should never use community
    policy_id: str
    consider_other_policies: List[str] = []
```

GFLBans will reply with the new Infraction object. You should apply the new restrictions yourself, however GFLBans will also push new state to the server using the RPC system

To implement the revocation code component of the spec, it is recommended that you store the id of the infraction in memory and associate it with a short, randomly generated code.

Should an admin use the revocation code, you should send a PATCH request to `/api/v1/infractions/INFRACTION_ID_HERE` with the following content

```json
{
  "admin": {
    "gs_admin": {
      "gs_service": "steam",
      "gs_id": "steamidhere"
    }
  },
  "set_removal_state": true,
  "removed_by": {
    "gs_admin": {
      "gs_service": "steam",
      "gs_id": "steamidhere"
    }
  },
  "removal_reason": "Revoked in-game using the revocation code."
}
```

GFLBans will reply with the altered infraction, but you can probably just ignore it. The revocation code should be removed once it is used.

***

If the plugin should notice that a tiering policy is no longer referenced, it is recommended to unlink the server from the tiering policy to prevent it from cluttering up the WebUI.

```python
class UnlinkInfractionTieringPolicy(BaseModel):
    policy_id: str
```

GFLBans will reply with a 204 once the policy has been unlinked. The server should delete the stored policy ID once it has been unlinked.

## Old style infractions

Some server managers may not with to use !punish, so GFLBans supports infractions that more closely resemble other admin mods too.

To make one of these infractions, POST to `/api/v1/infractions/` with something like this:

```python
class CreateInfraction:
    duration: Optional[PositiveInt]
    player: PlayerObjSimple
    admin: Optional[Initiator]
    reason: constr(min_length=1, max_length=280)
    punishments: List[constr(regex=valid_types_regex)]
    scope: constr(regex=r'^(server|global|community)$')  # the plugin should never use community
    session: bool = False
    dec_online_only: bool = False
```
|Field|Type|Description|
|---------|----|-----------|
|duration|Optional[PositiveInt]|The length of the infraction in seconds. **OMIT** entirely for a permanent length|
|player|PlayerObjSimple|Self explanatory. The player object|
|admin|Optional[Initiator]|The admin whom initiated the infraction. **OMIT** for console|
|reason|constr(min_length=1, max_length=280)|The reason behind the infraction|
|punishments|List[constr(regex=valid_types_regex)]|Valid punishments are `voice_block`, `chat_block`, `ban`, `admin_chat_block`, `call_admin_block`|
|scope|constr(regex=r'^(server\|global\|community)$')|Either `server` or `global`. The plugin should **never** use community|
|session|bool|Behaves just like in sourcebans when no length is specified. The infraction is set to expire instantly on the web site and the game server should maintain it throughout the map|
|dec_online_only|bool|Whether the infraction only decreases while the player is connected to the server. Doesn't work for `ban`|

GFLBans will reply with the new Infraction object. You should apply the new restrictions yourself, however GFLBans will also push new state to the server using the RPC system

***

## Removing infractions

GFLBans supports removing infractions by ID, but often admins want to remove all infractions applying to a player when they execute an in-game unban, so GFLBans supports this

To do this, you can send a POST request to `/api/v1/infractions/remove`.

The following must be sent in the body of the post request:

```python
class RemoveInfractionsOfPlayer:
    player: PlayerObjNoIp
    remove_reason: constr(min_length=1, max_length=280)
    admin: Optional[Initiator]
    include_other_servers: bool = True
    restrict_types: Optional[List[constr(regex=valid_types_regex)]]
```
|Field|Type|Description|
|---------|----|-----------|
|player|PlayerObjNoIp|Self explanatory. The player object|
|remove_reason|constr(min_length=1, max_length=280)|The infraction removal reason|
|admin|Optional[Initiator]|The admin that removed the infraction. **OMIT** for console|
|include_other_servers|bool|Remove `global` bans or `server` bans|
|restrict_types|Optional[List[constr(regex=valid_types_regex)]]|Valid types are `voice_block`, `chat_block`, `ban`, `admin_chat_block`, `call_admin_block`|

GFLBans will reply with:

```python
class RemoveInfractionsOfPlayerReply(BaseModel):
    num_removed: PositiveIntIncl0
    num_considered: PositiveIntIncl0
    num_not_removed: PositiveIntIncl0
```

You should invalidate any local state and either:

1. Wait for GFLBans to push new state via RPC
2. Send a new check request

***

## Getting infractions count

GFLBans allows you to get the number of past infractions applied on the player.  

To do this, you can send a GET request to `/api/v1/infractions/stats`  

The following parameters are accepted:

|Parameter|Type|Description|
|---------|----|-----------|
|gs_service|str|The service component of the player object, usually `steam`|
|gs_id|str|The id component of the player object. For steam, this is their steamid64|
|ip|str|The IP address of the player|
|include_other_servers|bool|Whether or not to accept global infractions issued on other servers. Should be configurable by the manager||

GFLBans will reply with:
```python
class InfractionStatisticReply(BaseModel):
    voice_block_count: PositiveIntIncl0
    text_block_count: PositiveIntIncl0
    ban_count: PositiveIntIncl0
    admin_chat_block_count: PositiveIntIncl0
    call_admin_block_count: PositiveIntIncl0
    warnings_count: PositiveIntIncl0
```