import asyncio

from packaging.version import Version
from pymongo import ReturnDocument

from gflbans.internal import shard
from gflbans.internal.config import MONGO_DB
from gflbans.internal.constants import GB_VERSION
from gflbans.internal.database.group import DGroup
from gflbans.internal.database.infraction import DInfraction
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

    if Version(old_version) < Version('0.9.0'):
        INFRACTION_SUPER_GLOBAL = 1 << 2  # Replaced with GLOBAL punishment
        INFRACTION_UNKNOWN_FEATURE = 1 << 15  # This was from before GFLBans was open source, no idea what it was

        INFRACTION_DEPRECATIONS = INFRACTION_SUPER_GLOBAL | INFRACTION_UNKNOWN_FEATURE
        async for inf in DInfraction.from_query(db, {'flags': {'$bitsAnySet': INFRACTION_DEPRECATIONS}}):
            inf.flags &= ~INFRACTION_DEPRECATIONS
            await inf.commit(db)

        PERMISSION_EDIT_OWN_INFRACTIONS = 1 << 4  # Was added to PERMISSION_CREATE_INFRACTION
        PERMISSION_PRUNE_INFRACTIONS = 1 << 10  # Was never implemented
        PERMISSION_VIEW_AUDIT_LOG = 1 << 11  # Was never implemented
        PERMISSION_SCOPE_SUPER_GLOBAL = 1 << 20  # Was replaced with PERMISSION_SCOPE_GLOBAL

        PERMISSION_DEPRECATIONS = (
            PERMISSION_EDIT_OWN_INFRACTIONS
            | PERMISSION_PRUNE_INFRACTIONS
            | PERMISSION_SCOPE_SUPER_GLOBAL
            | PERMISSION_VIEW_AUDIT_LOG
        )
        async for grp in DGroup.from_query(db, {'privileges': {'$bitsAnySet': PERMISSION_DEPRECATIONS}}):
            grp.privileges &= ~PERMISSION_DEPRECATIONS
            await grp.commit(db)

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
