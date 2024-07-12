import asyncio
from concurrent.futures.process import ProcessPoolExecutor
from hashlib import md5

import aiohttp
from aredis import StrictRedis, VERSION
from aredis.cache import IdentityGenerator
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING

from gflbans.internal import shard
from gflbans.internal.asn import IPInfoIdentityGenerator
from gflbans.internal.config import MONGO_URI, RETAIN_AUDIT_LOG_FOR, REDIS_URI, FORUMS_OAUTH_ACCESS_TOKEN_LIFETIME, \
    MONGO_DB
from gflbans.internal.integrations.games.discord import DiscordIdentityGenerator
from gflbans.internal.integrations.games.steam import SteamIdentityGenerator
from gflbans.internal.integrations.ips import IPSIdentityGenerator
from gflbans.internal.log import logger
from gflbans.internal.task import task_loop
from gflbans.internal.utils import ORJSONSerializer


def configure_app(app):
    app.state.db = AsyncIOMotorClient(MONGO_URI)

    app.state.redis_client = StrictRedis.from_url(REDIS_URI, db=3)

    class GlobalCacheIG(IdentityGenerator):
        def generate(self, key, typ):
            typ = md5(typ).hexdigest().upper()
            return 'global_cache::%s:%s' % (typ, key)

    class DBCacheIG(IdentityGenerator):
        def generate(self, key, typ):
            typ = md5(typ).hexdigest().upper()

            return 'db_cache::%s:%s' % (typ, key)

    app.state.cache = app.state.redis_client.cache('GlobalCache', identity_generator_class=GlobalCacheIG,
                                         serializer_class=ORJSONSerializer)

    app.state.discord_cache = app.state.redis_client.cache('DiscordCache', identity_generator_class=DiscordIdentityGenerator,
                                         serializer_class=ORJSONSerializer)

    app.state.steam_cache = app.state.redis_client.cache('SteamCache', identity_generator_class=SteamIdentityGenerator,
                                         serializer_class=ORJSONSerializer)

    app.state.ips_cache = app.state.redis_client.cache('IPSCache', identity_generator_class=IPSIdentityGenerator,
                                                        serializer_class=ORJSONSerializer)

    app.state.ip_info_cache = app.state.redis_client.cache('IPInfoCache',
                                                            identity_generator_class=IPInfoIdentityGenerator,
                                                            serializer_class=ORJSONSerializer)

    app.state.aio_session = aiohttp.ClientSession()

    app.state.sync_processes = ProcessPoolExecutor(max_workers=4)


async def gflbans_init(app):
    try:
        logger.info(f'gflbans v{VERSION}: API Shard Startup')
        logger.info(f'Using {shard} as shard identifier')

        logger.info('Connecting to MongoDB...')
        configure_app(app)

        # Groups
        await app.state.db[MONGO_DB].groups.create_index([('ips_group', ASCENDING)], unique=True)

        # Infractions
        await app.state.db[MONGO_DB].infractions.create_index([('created', DESCENDING)])
        await app.state.db[MONGO_DB].infractions.create_index([('expires', ASCENDING)])
        await app.state.db[MONGO_DB].infractions.create_index([('ip', ASCENDING)])
        await app.state.db[MONGO_DB].infractions.create_index([('user.gs_service', ASCENDING),
                                                               ('user.gs_id', ASCENDING)])

        # Admins
        await app.state.db[MONGO_DB].admin_cache.create_index([('ips_user', ASCENDING)], unique=True)

        # Blocks
        await app.state.db[MONGO_DB].blocks.create_index([('block_name', ASCENDING)], unique=True)

        # Avatars
        await app.state.db[MONGO_DB].fs.files.create_index([('metadata.retrieved_from', ASCENDING)],
                                                           name='gridfs_av_src_idx')

        # Map images
        await app.state.db[MONGO_DB].fs.files.create_index([('metadata.mod_name', ASCENDING),
                                                            ('metadata.map_name', ASCENDING)],
                                                           name='gridfs_mn_idx')

        # Call Admin images
        await app.state.db[MONGO_DB].fs.files.create_index([('metadata.dispose_created', ASCENDING)],
                                                           name='gridfs_cai_idx', expireAfterSeconds=2592000)

        # Sessions
        await app.state.db[MONGO_DB].sessions.create_index([('_id', ASCENDING),
                                                            ('session_token', ASCENDING)])

        await app.state.db[MONGO_DB].sessions.create_index([('created', ASCENDING)], background=True,
                                                           expireAfterSeconds=604800)

        # Signatures
        await app.state.db[MONGO_DB].signatures.create_index([
            ('signature', ASCENDING),
            ('mod', ASCENDING),
            ('user', ASCENDING)
        ], unique=True)

        # VPN
        await app.state.db[MONGO_DB].vpns.create_index([('added_on', ASCENDING)])
        await app.state.db[MONGO_DB].vpns.create_index([('payload', ASCENDING)], unique=True)

        # Tasks
        await app.state.db[MONGO_DB].tasks.create_index([('run_at', ASCENDING)], background=True)

        # Audit Log
        await app.state.db[MONGO_DB].action_log.create_index([('time', ASCENDING)], background=True,
                                                             expireAfterSeconds=RETAIN_AUDIT_LOG_FOR)

        # RPC Task queue
        await app.state.db[MONGO_DB].rpc.create_index([('time', ASCENDING)], background=True,
                                                      expireAfterSeconds=(60 * 15))

        await app.state.db[MONGO_DB].user_cache.create_index([('created', ASCENDING)], background=True,
                                                             expireAfterSeconds=(
                                                                         FORUMS_OAUTH_ACCESS_TOKEN_LIFETIME - 30))

        # GKV
        await app.state.db[MONGO_DB].value_store.create_index([('key', ASCENDING)], unique=True)

        # Confirmation Links
        await app.state.db[MONGO_DB].confirmations.create_index([('created', ASCENDING)], background=True,
                                                      expireAfterSeconds=(60 * 10))

        logger.info('Mongo Indexes created')

        logger.info('Spawning task scheduler')
        asyncio.get_event_loop().create_task(task_loop(app))

        # RPC Broker
        # app.state.rpc = ServerRPCBroker(app.state.redis_client, app)
        # await app.state.rpc.setup()
        # logger.info('Connected to RPC')
    except Exception:
        logger.critical('Application Startup failed.', exc_info=True)
        raise


async def gflbans_unload(app):
    await app.state.db.disconnect()
    await app.state.aio_session.close()
