from starlette.config import Config

config = Config('.env')

# Database configuration options
MONGO_URI = config('MONGO_URI', default=None)
MONGO_DB = config('DB_NAME', default='gflbans')

# Redis Configuration options
REDIS_URI = config('REDIS_URI', default='redis://127.0.0.1/3')

# gflbans General
ROOT_USER = config('ROOT_USER', cast=int, default=None)

MEDIA_URL = config('MEDIA_URL', default='https://bans.gflclan.com/media/')
STATIC_URL = config('STATIC_URL', default='https://bans.gflclan.com/static/')
HOST = config('HOST', default='bans.gflclan.com')

# Auto stacking infractions
AUTO_STACK_START_TIME = config('AUTO_STACK_START_TIME', cast=int, default=60 * 30)  # Duration if no infraction history
AUTO_STACK_MAX_AGE = config(
    'AUTO_STACK_MAX_AGE', cast=int, default=60 * 60 * 24 * 365
)  # Max age of previous infractions to stack with (based on their creation date)
AUTO_STACK_MULTIPLIER = config(
    'AUTO_STACK_MULTIPLIER', cast=float, default=2.0
)  # How much to multiply longest past duration by to get new duration

DISABLE_GUIDELINES = config('DISABLE_GUIDELINES', cast=bool, default=True)
PRODUCTION = config('PRODUCTION', cast=bool, default=True)
MAX_UPLOAD_SIZE = config('MAX_UPLOAD_SIZE', cast=int, default=(30 * 1024 * 1024))
RETAIN_AUDIT_LOG_FOR = config('RETAIN_AUDIT_LOG_FOR', cast=int, default=3600 * 24 * 30)
SERVER_CACHE_STALE_AFTER = config('SERVER_CACHE_STALE_AFTER', cast=int, default=600)
RETAIN_CHAT_LOG_FOR = config('RETAIN_CHAT_LOG_FOR', cast=int, default=3600 * 24 * 30)
SECRET_KEY = config('SECRET_KEY', default='testing')  # Required string, should be long and random!
BRANDING = config('BRANDING', default='gflbans')  # Replace all gflbans branding with your own branding
COMMUNITY_ICON = config(
    'COMMUNITY_ICON', default='https://bans.gflclan.com/static/images/gflbans256.png'
)  # Profile picture for discord embeds
GFLBANS_ICON = config(
    'GFLBANS_ICON', default='https://bans.gflclan.com/static/images/gflbans256.png'
)  # Branding for GFLBans in Discord embeds

# Integrations with other services
DISCORD_BOT_TOKEN = config('DISCORD_BOT_TOKEN', default=None)
GLOBAL_INFRACTION_WEBHOOK = config('GLOBAL_INFRACT_WEBHOOK', default=None)  # For global monitoring
STEAM_API_KEY = config('STEAM_API_KEY', default=None)
STEAM_OPENID_ACCESS_TOKEN_LIFETIME = config('STEAM_OPENID_ACCESS_TOKEN_LIFETIME', cast=int, default=604800)
IPHUB_API_KEY = config('IPHUB_API_KEY', default=None)
IPHUB_CACHE_TIME = config('IPHUB_CACHE_TIME', cast=int, default=(60 * 60 * 24 * 7))  # Seconds to cache IPHub results

# Web Server Configuration
WEB_USE_UNIX = config('WEB_USE_UNIX', default=True, cast=bool)  # True = use unix socket, False = use HTTP/TCP
WEB_UNIX = config('UNIX_SOCKET', default='/run/gflbans.sock')  # UDS to listen on.
WEB_PORT = config('HTTP_PORT', default=3335, cast=int)  # Port to listen on if using HTTP/TCP
WORKERS = config('GFLBANS_WORKERS', default=3, cast=int)
