from starlette.config import Config

config = Config('.env')

# Database configuration options
MONGO_URI = config('MONGO_URI', default=None)
MONGO_DB = config('DB_NAME', default='gflbans')

# Redis Configuration options
REDIS_URI = config('REDIS_URI', default='redis://127.0.0.1/3')

# IPS4 Options
STEAM_OPENID_ACCESS_TOKEN_LIFETIME = config('STEAM_OPENID_ACCESS_TOKEN_LIFETIME', cast=int, default=604800)
FORUMS_HOST = config('FORUMS_HOST')

# gflbans General
ROOT_USER = config('ROOT_USER', cast=int, default=None)

MEDIA_URL = config('MEDIA_URL', default='https://bans.gflclan.com/media/')
STATIC_URL = config('STATIC_URL', default='https://bans.gflclan.com/static/')
HOST = config('HOST', default='bans.gflclan.com')

PRODUCTION = config('PRODUCTION', cast=bool, default=True)
MAX_UPLOAD_SIZE = config('MAX_UPLOAD_SIZE', cast=int, default=(30 * 1024 * 1024))
RETAIN_AUDIT_LOG_FOR = config('RETAIN_AUDIT_LOG_FOR', cast=int, default=3600 * 24 * 30)
SERVER_CACHE_STALE_AFTER = config('SERVER_CACHE_STALE_AFTER', cast=int, default=600)
SIGNING_KEY = config('SECRET_KEY', default='testing')  # Required string, should be long and random!
BRANDING = config('BRANDING', default='gflbans')  # Replace all gflbans branding with your own branding
DEFAULT_PROFILE_PIC = config('DEFAULT_PROFILE_PIC', default='https://avatars.akamai.steamstatic.com/fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb_full.jpg') # Profile picture if user does not have one
COMMUNITY_ICON = config('COMMUNITY_ICON', default='https://gflusercontent.gflclan.com/file/forums-prod/monthly_2020_12/android-chrome-512x512.png') # Profile picture for discord embeds
GFLBANS_ICON = config('GFLBANS_ICON', default='https/bans.gflclan.com/static/images/gflbans256.png') # Branding for GFLBans in Discord embeds

# Integrations with other services
DISCORD_BOT_TOKEN = config('DISCORD_BOT_TOKEN', default=None)
STEAM_API_KEY = config('STEAM_API_KEY', default=None)
GLOBAL_INFRACTION_WEBHOOK = config('GLOBAL_INFRACT_WEBHOOK', default=None)  # For global monitoring

# Web Server Configuration
WEB_USE_UNIX = config('WEB_USE_UNIX', default=True, cast=bool)  # True = use unix socket, False = use HTTP/TCP
WEB_UNIX = config('UNIX_SOCKET', default='/run/gflbans.sock')  # UDS to listen on.
WEB_PORT = config('HTTP_PORT', default=3335, cast=int)  # Port to listen on if using HTTP/TCP
WORKERS = config('GFLBANS_WORKERS', default=3, cast=int)