import asyncio
from concurrent.futures.process import ProcessPoolExecutor
from hashlib import md5

import aiohttp
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING
from redis.asyncio import Redis

from gflbans.internal import shard
from gflbans.internal.config import (
    MONGO_DB,
    MONGO_URI,
    REDIS_URI,
    RETAIN_AUDIT_LOG_FOR,
    RETAIN_CHAT_LOG_FOR,
    STEAM_OPENID_ACCESS_TOKEN_LIFETIME,
)
from gflbans.internal.constants import GB_VERSION
from gflbans.internal.log import logger
from gflbans.internal.task import task_loop
from gflbans.internal.utils import ORJSONSerializer


class RedisCache:
    def __init__(self, redis_client, name, serializer):
        self.redis_client = redis_client
        self.name = name
        self.serializer = serializer

    def _generate_key(self, key, typ):
        typ = md5(typ.encode()).hexdigest().upper()
        return f'{self.name}::{typ}:{key}'

    async def set(self, key, value, typ, expire_time=None):
        cache_key = self._generate_key(key, typ)
        serialized_value = self.serializer.serialize(value)
        if expire_time:
            await self.redis_client.setex(cache_key, expire_time, serialized_value)
        else:
            await self.redis_client.set(cache_key, serialized_value)

    async def get(self, key, typ):
        cache_key = self._generate_key(key, typ)
        value = await self.redis_client.get(cache_key)
        return self.serializer.deserialize(value) if value else None


def configure_app(app):
    app.state.db = AsyncIOMotorClient(MONGO_URI)
    app.state.redis_client = Redis.from_url(REDIS_URI, db=3)

    app.state.cache = RedisCache(app.state.redis_client, 'GlobalCache', ORJSONSerializer())
    app.state.steam_cache = RedisCache(app.state.redis_client, 'SteamCache', ORJSONSerializer())
    app.state.ips_cache = RedisCache(app.state.redis_client, 'IPSCache', ORJSONSerializer())
    app.state.ip_info_cache = RedisCache(app.state.redis_client, 'IPInfoCache', ORJSONSerializer())

    app.state.aio_session = aiohttp.ClientSession()

    app.state.sync_processes = ProcessPoolExecutor(max_workers=4)


async def gflbans_init(app):
    try:
        logger.info(f'gflbans v{GB_VERSION}: API Shard Startup')
        logger.info(f'Using {shard} as shard identifier')

        logger.info('Connecting to MongoDB...')
        configure_app(app)

        # Groups
        await app.state.db[MONGO_DB].groups.create_index([('ips_group', ASCENDING)], unique=True)

        # Infractions
        await app.state.db[MONGO_DB].infractions.create_index([('created', DESCENDING)])
        await app.state.db[MONGO_DB].infractions.create_index([('expires', ASCENDING)])
        await app.state.db[MONGO_DB].infractions.create_index([('ip', ASCENDING)])
        await app.state.db[MONGO_DB].infractions.create_index(
            [('user.gs_service', ASCENDING), ('user.gs_id', ASCENDING)]
        )

        # Message logs
        await app.state.db[MONGO_DB].chat_logs.create_index(
            [('created', ASCENDING)], background=True, expireAfterSeconds=RETAIN_CHAT_LOG_FOR
        )
        await app.state.db[MONGO_DB].chat_logs.create_index('server')
        await app.state.db[MONGO_DB].chat_logs.create_index([('user.gs_service', ASCENDING), ('user.gs_id', ASCENDING)])

        # Admins
        await app.state.db[MONGO_DB].admin_cache.create_index([('ips_user', ASCENDING)], unique=True)

        # Blocks
        await app.state.db[MONGO_DB].blocks.create_index([('block_name', ASCENDING)], unique=True)

        # Avatars
        await app.state.db[MONGO_DB].fs.files.create_index(
            [('metadata.retrieved_from', ASCENDING)], name='gridfs_av_src_idx'
        )

        # Map images
        await app.state.db[MONGO_DB].fs.files.create_index(
            [('metadata.mod_name', ASCENDING), ('metadata.map_name', ASCENDING)], name='gridfs_mn_idx'
        )

        # Call Admin images
        await app.state.db[MONGO_DB].fs.files.create_index(
            [('metadata.dispose_created', ASCENDING)], name='gridfs_cai_idx', expireAfterSeconds=2592000
        )

        # Sessions
        await app.state.db[MONGO_DB].sessions.create_index([('_id', ASCENDING), ('session_token', ASCENDING)])

        await app.state.db[MONGO_DB].sessions.create_index(
            [('created', ASCENDING)], background=True, expireAfterSeconds=STEAM_OPENID_ACCESS_TOKEN_LIFETIME
        )

        # VPN
        await app.state.db[MONGO_DB].vpns.create_index([('added_on', ASCENDING)])
        await app.state.db[MONGO_DB].vpns.create_index([('payload', ASCENDING)], unique=True)

        # Tasks
        await app.state.db[MONGO_DB].tasks.create_index([('run_at', ASCENDING)], background=True)

        # Audit Log
        await app.state.db[MONGO_DB].action_log.create_index(
            [('time', ASCENDING)], background=True, expireAfterSeconds=RETAIN_AUDIT_LOG_FOR
        )

        # RPC Task queue
        await app.state.db[MONGO_DB].rpc.create_index(
            [('time', ASCENDING)], background=True, expireAfterSeconds=(60 * 15)
        )

        await app.state.db[MONGO_DB].user_cache.create_index(
            [('created', ASCENDING)], background=True, expireAfterSeconds=(STEAM_OPENID_ACCESS_TOKEN_LIFETIME - 30)
        )

        # GKV
        await app.state.db[MONGO_DB].value_store.create_index([('key', ASCENDING)], unique=True)

        # Confirmation Links
        await app.state.db[MONGO_DB].confirmations.create_index(
            [('created', ASCENDING)], background=True, expireAfterSeconds=(60 * 10)
        )

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
