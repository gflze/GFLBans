from gflbans.internal.database.kv import PersistentKV

async def get_var(db_ref, key, default=None):
    result = await PersistentKV.find_one_from_query(db_ref, {'key': key})

    if result is None:
        return default
    else:
        return result.value

async def set_var(db_ref, key, value):
    pkv = await PersistentKV.find_one_from_query(db_ref, {'key': key})

    if pkv is None:
        pkv = PersistentKV(key=key, value=value)
    else:
        await pkv.update_field(db_ref, 'value', value)
        return
    
    await pkv.commit(db_ref)