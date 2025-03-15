# PERMISSION FLAGS
# These are given to API Keys, Groups, and Server keys to determine what actions they may perform
PERMISSION_LOGIN                    = 1 << 0   # Login to the website
PERMISSION_COMMENT                  = 1 << 1
PERMISSION_VIEW_IP_ADDR             = 1 << 2
PERMISSION_CREATE_INFRACTION        = 1 << 3
PERMISSION_VIEW_CHAT_LOGS           = 1 << 4
PERMISSION_EDIT_ALL_INFRACTIONS     = 1 << 5
PERMISSION_ATTACH_FILE              = 1 << 6
PERMISSION_WEB_MODERATOR            = 1 << 7   # Can edit or delete all comments/files on infractions
PERMISSION_MANAGE_SERVERS           = 1 << 8
PERMISSION_MANAGE_VPNS              = 1 << 9
# PERMISSION_PRUNE_INFRACTIONS      = 1 << 10  # Unimplemented
# PERMISSION_VIEW_AUDIT_LOG         = 1 << 11  # Unimplemented
PERMISSION_MANAGE_GROUPS_AND_ADMINS = 1 << 12
PERMISSION_MANAGE_API_KEYS          = 1 << 13
PERMISSION_BLOCK_ITEMS              = 1 << 14  # Add map item restrictions to infractions
PERMISSION_BLOCK_VOICE              = 1 << 15  # Add voice blocks to infractions
PERMISSION_BLOCK_CHAT               = 1 << 16  # Add chat blocks to infractions
PERMISSION_BAN                      = 1 << 17  # Add bans to infractions
PERMISSION_ADMIN_CHAT_BLOCK         = 1 << 18  # Block admin chat
PERMISSION_CALL_ADMIN_BLOCK         = 1 << 19  # Block call admin usage
# PERMISSION_SCOPE_SUPER_GLOBAL     = 1 << 20  # DEPRECATED
PERMISSION_SCOPE_GLOBAL             = 1 << 21  # Admins can scope infractions globally
PERMISSION_VPN_CHECK_SKIP           = 1 << 22  # Users with this permission are immune to VPN kicks
PERMISSION_MANAGE_POLICY            = 1 << 23  # Manage tiering policies
PERMISSION_IMMUNE                   = 1 << 24  # Immune from infractions
PERMISSION_SKIP_IMMUNITY            = 1 << 25  # Overrides immunity
PERMISSION_RPC_KICK                 = 1 << 26
PERMISSION_ASSIGN_TO_SERVER         = 1 << 27  # Assign an infraction to a specific server
PERMISSION_MANAGE_MAP_ICONS         = 1 << 28  # Upload and delete map icons

# Can't just do (1 << 29) - 1 due to deprecated permissions in the middle
ALL_PERMISSIONS = (
    PERMISSION_LOGIN
    | PERMISSION_COMMENT
    | PERMISSION_VIEW_IP_ADDR
    | PERMISSION_CREATE_INFRACTION
    | PERMISSION_VIEW_CHAT_LOGS
    | PERMISSION_EDIT_ALL_INFRACTIONS
    | PERMISSION_ATTACH_FILE
    | PERMISSION_WEB_MODERATOR
    | PERMISSION_MANAGE_SERVERS
    | PERMISSION_MANAGE_VPNS
    | PERMISSION_MANAGE_GROUPS_AND_ADMINS
    | PERMISSION_MANAGE_API_KEYS
    | PERMISSION_BLOCK_ITEMS
    | PERMISSION_BLOCK_VOICE
    | PERMISSION_BLOCK_CHAT
    | PERMISSION_BAN
    | PERMISSION_ADMIN_CHAT_BLOCK
    | PERMISSION_CALL_ADMIN_BLOCK
    | PERMISSION_SCOPE_GLOBAL
    | PERMISSION_VPN_CHECK_SKIP
    | PERMISSION_MANAGE_POLICY
    | PERMISSION_IMMUNE
    | PERMISSION_SKIP_IMMUNITY
    | PERMISSION_RPC_KICK
    | PERMISSION_ASSIGN_TO_SERVER
    | PERMISSION_MANAGE_MAP_ICONS
)

# This isn't a permission node, but a hard coded value for what may be done by a server acting as system
# If the server isn't acting as system, they are limited by both SERVER_KEY_PERMISSIONS and the user's permissions
# (The server key perms are checked first, then the user's)
SERVER_KEY_PERMISSIONS = (
    PERMISSION_COMMENT
    | PERMISSION_VIEW_IP_ADDR
    | PERMISSION_CREATE_INFRACTION
    | PERMISSION_EDIT_ALL_INFRACTIONS
    | PERMISSION_ATTACH_FILE
    | PERMISSION_BLOCK_CHAT
    | PERMISSION_BLOCK_VOICE
    | PERMISSION_BAN
    | PERMISSION_BLOCK_ITEMS
    | PERMISSION_ADMIN_CHAT_BLOCK
    | PERMISSION_CALL_ADMIN_BLOCK
    | PERMISSION_SCOPE_GLOBAL
    | PERMISSION_MANAGE_POLICY
    | PERMISSION_SKIP_IMMUNITY
)

str2permflag = {
    'voice_block':      PERMISSION_BLOCK_VOICE,
    'chat_block':       PERMISSION_BLOCK_CHAT,
    'ban':              PERMISSION_BAN,
    'admin_chat_block': PERMISSION_ADMIN_CHAT_BLOCK,
    'call_admin_block': PERMISSION_CALL_ADMIN_BLOCK,
    'item_block':       PERMISSION_BLOCK_ITEMS,
}

name2perms = {
    'Can Login':                 PERMISSION_LOGIN,
    'Can Comment':               PERMISSION_COMMENT,
    'Can See IP Addresses':      PERMISSION_VIEW_IP_ADDR,
    'Add Infractions':           PERMISSION_CREATE_INFRACTION,
    'View Chat Logs':            PERMISSION_VIEW_CHAT_LOGS,
    'Edit All Infractions':      PERMISSION_EDIT_ALL_INFRACTIONS,
    'Attach Files':              PERMISSION_ATTACH_FILE,
    'Edit All Comments':         PERMISSION_WEB_MODERATOR,
    'Manage Servers':            PERMISSION_MANAGE_SERVERS,
    'Manage VPNs':               PERMISSION_MANAGE_VPNS,
    'Manage Groups and Admins':  PERMISSION_MANAGE_GROUPS_AND_ADMINS,
    'Manage API Keys':           PERMISSION_MANAGE_API_KEYS,
    'Restrict Voice':            PERMISSION_BLOCK_VOICE,
    'Restrict Text':             PERMISSION_BLOCK_CHAT,
    'Ban':                       PERMISSION_BAN,
    'Restrict Admin Chat':       PERMISSION_ADMIN_CHAT_BLOCK,
    'Restrict Call Admin':       PERMISSION_CALL_ADMIN_BLOCK,
    'Add Global Infractions':    PERMISSION_SCOPE_GLOBAL,
    'VPN Kick Immunity':         PERMISSION_VPN_CHECK_SKIP,
    'Manage Tiering Policies':   PERMISSION_MANAGE_POLICY,
    'Immune from Infractions':   PERMISSION_IMMUNE,
    'Overrides Immunity':        PERMISSION_SKIP_IMMUNITY,
    'RPC Kick':                  PERMISSION_RPC_KICK,
    'Assign an Infraction to a Specific Server': PERMISSION_ASSIGN_TO_SERVER,
    'Upload and Delete Map Icons': PERMISSION_MANAGE_MAP_ICONS,
    'Restrict Map Items':        PERMISSION_BLOCK_ITEMS,
}

# INFRACTION FLAGS
# These are given to infraction objects to indicate some basic information about them
INFRACTION_SYSTEM               = 1 << 0   # Created by SYSTEM
INFRACTION_GLOBAL               = 1 << 1   # The ban applies to all servers except those ignoring globals
# INFRACTION_SUPER_GLOBAL       = 1 << 2   # DEPRECATED
INFRACTION_PERMANENT            = 1 << 3   # The ban does not expire
INFRACTION_VPN                  = 1 << 4   # The IP associated with the ban is likely a VPN (Doesn't show up in check by ip)
INFRACTION_WEB                  = 1 << 5   # The infraction was created via the web panel (thus has no server associated with it)
INFRACTION_REMOVED              = 1 << 6   # The ban was removed by an admin. It still appears, but is not active
INFRACTION_VOICE_BLOCK          = 1 << 7   # The player may not speak in game
INFRACTION_CHAT_BLOCK           = 1 << 8   # The player may not type in game
INFRACTION_BAN                  = 1 << 9   # The player may not join the server
INFRACTION_ADMIN_CHAT_BLOCK     = 1 << 10  # The player may not use admin chat
INFRACTION_CALL_ADMIN_BAN       = 1 << 11  # The player may not call an admin (using !calladmin)
INFRACTION_SESSION              = 1 << 12  # Infraction expires immediately on web, and duration is handled by the game server
INFRACTION_PLAYTIME_DURATION    = 1 << 13  # Only reduces duration when player is online. Invalid for bans and web infractions
INFRACTION_ITEM_BLOCK           = 1 << 14  # The player may not use map spawned items
#                                 1 << 15  # DEPRECATED
INFRACTION_AUTO_TIER            = 1 << 16  # This infraction is considered for tiering purposes.

scope_to_flag = {
    'server':    0,
    'global':    INFRACTION_GLOBAL,
}

str2pflag = {
    'voice_block':      INFRACTION_VOICE_BLOCK,
    'chat_block':       INFRACTION_CHAT_BLOCK,
    'ban':              INFRACTION_BAN,
    'admin_chat_block': INFRACTION_ADMIN_CHAT_BLOCK,
    'call_admin_block': INFRACTION_CALL_ADMIN_BAN,
    'item_block':       INFRACTION_ITEM_BLOCK,
}

valid_types_regex = '^('

_f = True

for t in str2pflag:
    if _f:
        valid_types_regex = valid_types_regex + t
        _f = False
    else:
        valid_types_regex = valid_types_regex + '|' + t

valid_types_regex = valid_types_regex + ')$'
