## GFLBans API for Plugins

This document contains the necessary information to implement a basic gflbans plugin.

The gflbans API can be found at the /api/v1/ route of the main instance. For example, if your instance is hosted at bans.gflclan.com, the api would be at bans.gflclan.com/api/v1/

The following subroutes make up the api

|Route|Description|
|-----|-----------|
|/infractions|All infraction related operations|
|/gs|Misc. routes useful to the gflbans plugin|
|/rpc|Routes that can be used by the gflbans plugin to receive data from gflbans|

There are other subroutes, but they aren't useful for the plugin

### Authentication

All API requests should be authenticated using the Authorization header.

```
Authorization: SERVER SERVER_ID SERVER_KEY
```

SERVER_ID and SERVER_KEY are user supplied parameters. Make sure the user can configure them.

### Common structures

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
    ip: str

# SEND ONLY ONE OF THESE FIELDS
class Initiator:
    ips_id: Optional[PositiveInt]
    mongo_id: Optional[str]
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

### Heartbeat

The gflbans plugin should periodically send data to gflbans so that gflbans can:

 - Know if the server is alive
 - Update infractions that only decrement while the player is online
 - Display information about the server in the Web UI

The heartbeat route is present at /api/v1/gs/heartbeat and should be POSTed do with JSON data in the following format:

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

The `mod` is the name of the game folder (garrysmod for gmod, csgo for csgo, cstrike for css).
`locked` is whether `sv_password` is set so that only people with the password can join.
If the plugin configuration wants to accept GLOBAL gflbans, `include_other_servers` should be true, otherwise false.
The rest of the parameters should be self explanatory.

The API will reply with a list of HeartbeatChange objects:

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
You can omit call_admin_blocks from the local state since gflbans enforces them server side.

It is recommended that a heartbeat is sent each minute, though servers can get away with doing as much as 10 minutes in between beats

### RPC Events

gflbans uses RPC events to tell the server to do things and to inform it of changes. RPC events can be retrieved by polling /api/v1/rpc/poll or sent as they become available by listening on Websocket /api/v1/rpc/ws

RPC event responses have the generic form

```python
class RPCEventBase:
    event_id: str
    time: datetime
    event: str
```

The event_id field is a unique id that gflbans can use to idenify events. The time is the time the event was created. The event is the event type.

Each event type has it's own fields

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

### Checking player infractions

gflbans will send events to the server, however, when a player first joins, you should check a player's infractions to establish their initial state.

To retrieve a player's information, send a GET request to /api/v1/infractions/check

The following parameters are accepted:

|Parameter|Type|Description|
|---------|----|-----------|
|gs_service|str|The service component of the player object, usually `steam`|
|gs_id|str|The id component of the player object. For steam, this is their steamid64|
|ip|str|The IP address of the player|
|include_other_servers|str|Whether or not to accept global infractions issued on other servers. Should be configurable by the manager||

gflbans will reply with an object like:

```python
class CheckInfractionsReply:
    voice_block: Optional[CInfractionSummary]
    chat_block: Optional[CInfractionSummary]
    ban: Optional[CInfractionSummary]
    admin_chat_block: Optional[CInfractionSummary]
    call_admin_block: Optional[CInfractionSummary]

class CInfractionSummary:
    expiration: Optional[PositiveInt]
    reason: str
    admin_name: str
```

You should use this to reject the players connection / kick them if they are banned, or apply other restrictions.

For the sake of being user friendly, it is recommended that you inform the player of the admin that banned, muted, or gagged them and the reason for which they were punished.

It is unnecessary to take action for `call_admin_block` as that is handled by gflbans web. Furthermore, `admin_chat_block` can be ignored if there is no admin chat function.

### Utilising VPN features

You can use gflbans' built in VPN detection by sending a GET request to /api/v1/gs/vpn on player join. The route accepts the following parameters:

|Parameter|Type|Description|
|---------|----|-----------|
|gs_service|str|The service component of the player object, usually `steam`|
|gs_id|str|The id component of the player object. For steam, this is their steamid64|
|ip|str|The player's ip address|

gflbans will reply with something like this

```python
class CheckVPNReply:
    is_vpn: bool
    is_cloud_gaming: bool
    is_immune: bool
```

The plugin is recommended to inform admins about a player joining with a vpn if `is_vpn` is true.

Depending on plugin configuration, the server may also kick them. If `is_immune` is set, the player should not be kicked.

The server may choose how to handle `is_cloud_gaming` depending on whether or not they want to allow or kick cloud gaming services.

### Calling an admin

You can utilise gflbans' implementation of call admin by sending a POST request to /api/v1/gs/calladmin

The calladmin route is rate limited and may only be called once per 10 minutes. Rate limiting is controlled by gflbans

The POST sent to gflbans should look like this:

```python
class ExecuteCallAdmin:
    caller: PlayerObjNoIp
    caller_name: str
    include_other_servers: bool = False
    message: constr(min_length=1, max_length=120)
```

Most of the parameters should be self-explanatory. The include_other_servers parameter should be true if the server is accepting global bans, but false if the server is ignoring them.

gflbans will send a reply that looks like this:

```python
class ExecuteCallAdminReply:
    sent: bool
    is_banned: bool
    cooldown: Optional[PositiveIntIncl0]
```

The player should be informed if an admin was called, how much cooldown remains, and whether they are banned from using call admin.

### Creating an infraction using tiering policies

If you want to implement https://gflclan.com/forums/topic/68218-new-punishment-system-for-gflbans-03-beta/ (which you should), these APi routes will let you do it.

The first component of this is registering an infraction template with gflbans. This should be done before any bans would be made, probably during plugin init.

The infraction template should only be registered once. You should check to see if you have a policy_id for the offense code before trying again.

You can register the template by POSTing to /api/v1/infractions/register_policy

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

gflbans will reply with

```python
class RegisterInfractionTieringPolicyReply:
    policy_id: str
```

policy_id is a unique id of the newly created tiering policy that gflbans uses to identify the saved configuration.

You should save this in local storage (sqlite, config file, etc) and associate it with the offense code as laid out in the above forum post.

When you'd actually like to ban a player, you can POST to /api/v1/infractions/using_policy with the following:

```python
class CreateInfractionUsingPolicy(BaseModel):
    player: PlayerObjSimple
    admin: Optional[Initiator]
    reason_override: Optional[constr(min_length=1, max_length=280)]
    scope: constr(regex=r'^(server|global|community)$')  # the plugin should never use community
    policy_id: str
    consider_other_policies: List[str] = []
```

gflbans will reply with the new Infraction object. You should apply the new restrictions yourself, however gflbans will also push new state to the server using the RPC system

To implement the revocation code component of the spec, it is recommended that you store the id of the infraction in memory and associate it with a short, randomly generated code.

Should an admin use the revocation code, you should send a PATCH request to /api/v1/infractions/INFRACTION_ID_HERE with the following content

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

gflbans will reply with the altered infraction, but you can probably just ignore it. The revocation code should be removed once it is used.

### Old style infractions

Some server managers may not with to use !punish, so gflbans supports infractions that more closely resemble other admin mods too.

To make one of these infractions, POST to /api/v1/infractions/ with something like this:

```python
class CreateInfraction:
    duration: Optional[PositiveInt]
    player: PlayerObjSimple
    admin: Optional[Initiator]
    reason: constr(min_length=1, max_length=280)
    punishments: List[constr(regex=valid_types_regex)]
    scope: constr(regex=r'^(server|global|community)$')  # don't use community!
    session: bool = False
    dec_online_only: bool = False
```

`include_other_servers` is whether or not the server is accepting globals
`punishments` should be one of `voice_block`, `chat_block`, `ban`, `admin_chat_block`, or `call_admin_block`
`duration` is the length of the infraction in seconds. OMIT entirely for permanent.
`dec_online_only` is whether or not the infraction only decreases while the player is connected to the server. Doesn't work with `ban`
`session` behaves just like in sourcebans. The infraction is set to expire instantly on the web site and the game server should maintain it throughout the map

gflbans will reply with the new Infraction object. You should apply the new restrictions yourself, however gflbans will also push new state to the server using the RPC system

### Removing infractions

gflbans supports removing infractions by ID, but often admins want to remove all infractions applying to a player when they execute an in-game unban, so gflbans supports this

To do this, you can send a DELETE request to /api/v1/infractions

The following must be sent in the body of the delete request:

```python
class RemoveInfractionsOfPlayer:
    player: PlayerObjNoIp
    remove_reason: constr(min_length=1, max_length=280)
    admin: Optional[Initiator]
    include_other_servers: bool = True
```

gflbans will reply with:

```python
class RemoveInfractionsOfPlayerReply(BaseModel):
    num_removed: PositiveIntIncl0
    num_considered: PositiveIntIncl0
    num_not_removed: PositiveIntIncl0
```

You should invalidate any local state and either

A) Wait for gflbans to push new state via RPC
B) Send a new check request