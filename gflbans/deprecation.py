import asyncio
from datetime import datetime, timedelta
from math import ceil

from dateutil.tz import UTC
from packaging.version import Version
from pymongo import ReturnDocument

from gflbans.internal import shard
from gflbans.internal.config import IPHUB_API_KEY, MONGO_DB
from gflbans.internal.constants import GB_VERSION
from gflbans.internal.database.group import DGroup
from gflbans.internal.database.infraction import DInfraction
from gflbans.internal.database.task import DTask
from gflbans.internal.flags import INFRACTION_VPN
from gflbans.internal.log import logger


async def deprecation_cleanup(app):
    DATABASE_INFO_KEY = 'gflbans_info'
    db = app.state.db[MONGO_DB]
    info_collection = db['version_info']

    version_info = await info_collection.find_one({'_id': DATABASE_INFO_KEY})

    if version_info is None:
        old_version = '0.8.0'  # Unknown version, assume 0.8.0 (or new database)
    elif 'old_version' in version_info:
        old_version = version_info['old_version']
    elif Version(version_info['version']) < Version(GB_VERSION):
        old_version = version_info['version']
    elif Version(version_info['version']) > Version(GB_VERSION):
        # Downgraded to an older version of GFLBans.
        # Update database version so cleanup can happen again when we update in the future
        await info_collection.find_one_and_update(
            {'_id': DATABASE_INFO_KEY},
            {
                '$set': {
                    'version': GB_VERSION,
                },
            },
        )
        return
    else:
        return  # Version is current, no cleanup needed

    version_info = await info_collection.find_one_and_update(
        {'_id': DATABASE_INFO_KEY},
        {
            '$setOnInsert': {'_id': DATABASE_INFO_KEY},
            '$set': {
                'version': GB_VERSION,
                'old_version': old_version,
                'updating_shard': shard,
            },
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )

    await asyncio.sleep(1)
    version_info = await info_collection.find_one({'_id': DATABASE_INFO_KEY})

    # To only run deprecation_cleanup once, only 1 shard should be allowed to run it
    if version_info['updating_shard'] != shard:
        return

    logger.info(f'Updating database from v{old_version} to v{GB_VERSION} on API Shard {shard}.')

    INFRACTION_DEPRECATIONS = 0
    PERMISSION_DEPRECATIONS = 0

    if Version(old_version) < Version('0.9.0'):
        PERMISSION_DEPRECATIONS |= (
            (1 << 4)  # PERMISSION_EDIT_OWN_INFRACTIONS, was added to PERMISSION_CREATE_INFRACTION
            | (1 << 10)  # PERMISSION_PRUNE_INFRACTIONS, was never implemented
            | (1 << 20)  # PERMISSION_SCOPE_SUPER_GLOBAL, was replaced with PERMISSION_SCOPE_GLOBAL
            | (1 << 11)  # PERMISSION_VIEW_AUDIT_LOG, was never implemented
        )

        INFRACTION_DEPRECATIONS |= (
            (1 << 2)  # INFRACTION_SUPER_GLOBAL, replaced with GLOBAL punishment
            | (1 << 15)  # This was from before GFLBans was open source, no idea what it was
        )

    if Version(old_version) < Version('1.0.0'):
        PERMISSION_DEPRECATIONS |= 1 << 4  # PERMISSION_MANAGE_POLICY, tiering policies were removed
        INFRACTION_DEPRECATIONS |= 1 << 16  # INFRACTION_AUTO_TIER, tiering policies were removed

    if Version(old_version) < Version('1.2.0') and 'action_log' in await db.list_collection_names():
        await db.drop_collection('action_log')  # Old log format, now uses audit_log instead

    if PERMISSION_DEPRECATIONS > 0:
        async for grp in DGroup.from_query(db, {'privileges': {'$bitsAnySet': PERMISSION_DEPRECATIONS}}):
            grp.privileges &= ~PERMISSION_DEPRECATIONS
            await grp.commit(db)

    if INFRACTION_DEPRECATIONS > 0:
        async for inf in DInfraction.from_query(db, {'flags': {'$bitsAnySet': INFRACTION_DEPRECATIONS}}):
            inf.flags &= ~INFRACTION_DEPRECATIONS
            await inf.commit(db)

    await info_collection.find_one_and_update(
        {'_id': DATABASE_INFO_KEY},
        {
            '$unset': {
                'updating_shard': None,
                'old_version': None,
            },
            '$set': {
                'version': GB_VERSION,
            },
        },
    )
    logger.info(f'Updated from {old_version} to {GB_VERSION} and removed deprecated features.')


async def full_vpn_check(app):
    DATABASE_INFO_KEY = 'gflbans_info'
    db = app.state.db[MONGO_DB]
    info_collection = db['version_info']

    version_info = await info_collection.find_one({'_id': DATABASE_INFO_KEY})

    # Only do a full re-check on infraction IPs being a VPN if it was never done
    if (
        version_info is None
        or version_info.get('vpn_backfill_done', False)
        or not IPHUB_API_KEY
        or IPHUB_API_KEY == 'APIKEYHERE'
    ):
        return

    version_info = await info_collection.find_one_and_update(
        {'_id': DATABASE_INFO_KEY},
        {
            '$setOnInsert': {'_id': DATABASE_INFO_KEY},
            '$set': {'vpn_check_shard': shard},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )

    await asyncio.sleep(1)
    version_info = await info_collection.find_one({'_id': DATABASE_INFO_KEY})

    # To only run full_vpn_check once, only 1 shard should be allowed to run it
    if version_info.get('vpn_check_shard') != shard:
        return

    DAILY_LIMIT = 500  # 1k is daily limit for free key on IPHub
    now = datetime.now(tz=UTC)

    cursor = db['infractions'].find(
        {'ip': {'$exists': True, '$ne': None}, 'flags': {'$bitsAllClear': INFRACTION_VPN}},
        {'_id': 1},
        sort=[('_id', 1)],
    )

    i = 0
    async for doc in cursor:
        inf_id = doc['_id']

        day_offset = i // DAILY_LIMIT
        slot_in_day = i % DAILY_LIMIT
        run_time = now + timedelta(days=day_offset, seconds=slot_in_day * 60)  # 1-min spacing

        task = DTask(
            run_at=run_time.timestamp(),
            task_data={'i_id': inf_id},
            ev_handler='get_vpn_data',
        )
        await task.commit(db)

        i += 1

    logger.info(f'Scheduled {i} VPN check tasks over {ceil(i / DAILY_LIMIT)} days.')

    # Mark backfill as done
    await info_collection.update_one(
        {'_id': DATABASE_INFO_KEY},
        {
            '$set': {'vpn_backfill_done': True},
            '$unset': {'vpn_check_shard': None},
        },
    )
