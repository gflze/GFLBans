from starlette.config import Config

config = Config('.env')

# Database configuration options
MONGO_URI = config('MONGO_URI', default=None)
MONGO_DB = config('DB_NAME', default='gflbans')

# Redis Configuration options
REDIS_URI = config('REDIS_URI', default='redis://127.0.0.1/3')

# IPS4 Options
FORUMS_API_PATH = config('FORUMS_API_PATH', default=None)
FORUMS_OAUTH_CLIENT_ID = config('FORUMS_CLIENT_ID', default=None)
FORUMS_OAUTH_CLIENT_SECRET = config('FORUMS_CLIENT_SECRET', default=None)
FORUMS_OAUTH_AUTH_URL = config('FORUMS_OAUTH_AUTH_ENDPOINT', default=None)
FORUMS_OAUTH_TOKEN_URL = config('FORUMS_OAUTH_TOKEN_ENDPOINT', default=None)
FORUMS_OAUTH_ACCESS_TOKEN_LIFETIME = config('FORUMS_OAUTH_ACCESS_TOKEN_LIFETIME', cast=int, default=604800)
FORUMS_OAUTH_REFRESH_TOKEN_LIFETIME = config('FORUMS_OAUTH_REQUEST_TOKEN_LIFETIME', cast=int, default=2419000)
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

# Integrations with other services
DISCORD_BOT_TOKEN = config('DISCORD_BOT_TOKEN', default=None)
STEAM_API_KEY = config('STEAM_API_KEY', default=None)
GLOBAL_INFRACTION_WEBHOOK = config('GLOBAL_INFRACT_WEBHOOK', default=None)  # For global monitoring

# Web Server Configuration
WEB_USE_UNIX = config('USE_UNIX', default=True, cast=bool)  # True = use unix socket, False = use HTTP/TCP
WEB_UNIX = config('UNIX_SOCKET', default='/run/gflbans.sock')  # UDS to listen on.
WEB_PORT = config('HTTP_PORT', default=3335, cast=int)  # Port to listen on if using HTTP/TCP
WORKERS = config('GFLBANS_WORKERS', default=3, cast=int)