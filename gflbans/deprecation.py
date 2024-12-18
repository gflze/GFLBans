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
        INFRACTION_DEPRECATED_FEATURE = 1 << 15  # This was from before GFLBans was open source, no idea what it was
        async for inf in DInfraction.from_query(db, {'flags': {'$bitsAllSet': INFRACTION_DEPRECATED_FEATURE}}):
            inf.flags &= ~INFRACTION_DEPRECATED_FEATURE
            await inf.commit(db)

        PERMISSION_EDIT_OWN_INFRACTIONS = 1 << 4
        async for grp in DGroup.from_query(db, {'privileges': {'$bitsAllSet': PERMISSION_EDIT_OWN_INFRACTIONS}}):
            grp.privileges &= ~PERMISSION_EDIT_OWN_INFRACTIONS
            await grp.commit(db)

    await info_collection.find_one_and_update(
        {'_id': DATABASE_INFO_KEY},
        {
            '$setOnInsert': {'_id': DATABASE_INFO_KEY},
            '$unset': {
                'updating_shard': None,
                'old_version': None,
            },
            '$set': {
                'version': GB_VERSION,
            },
        },
        upsert=True,
    )
    logger.info(f'Updated from {old_version} to {GB_VERSION} and removed deprecated features.')
