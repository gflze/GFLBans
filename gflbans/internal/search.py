import asyncio
import os
import re
from concurrent.futures.process import ProcessPoolExecutor
from functools import partial

from pymongo import MongoClient

from defusedxml import ElementTree

from gflbans.internal.config import MONGO_URI, MONGO_DB
from gflbans.internal.errors import SearchError
from gflbans.internal.flags import INFRACTION_SYSTEM, INFRACTION_PERMANENT, INFRACTION_SUPER_GLOBAL, INFRACTION_GLOBAL, \
    INFRACTION_VPN, INFRACTION_WEB, INFRACTION_REMOVED, INFRACTION_VOICE_BLOCK, INFRACTION_CHAT_BLOCK, INFRACTION_BAN, \
    INFRACTION_ADMIN_CHAT_BLOCK, INFRACTION_CALL_ADMIN_BAN, INFRACTION_SESSION
from gflbans.internal.log import logger

executor = ProcessPoolExecutor(max_workers=3)


# Find admins with that ips id
def ips_id_to_mongo_object_id(s: str):
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    col = db.admin_cache

    r = col.find_one({'ips_user': int(s)})

    if r is None:
        return str(os.urandom(32).hex())  # This should result in the search returning nothing.

    return r['_id']


def admin_name_mongo_ids(s: str):
    client = MongoClient(MONGO_URI)
    col = client[MONGO_DB].admin_cache

    r = [doc['_id'] for doc in col.find({'name': {'$regex': s, '$options': 'i'}})]

    if len(r) <= 0:
        return str(os.urandom(32).hex())

    return r


def server_ip_port_to_mongo_id(s: str):
    client = MongoClient(MONGO_URI)
    col = client[MONGO_DB].servers

    a = s.split(':')

    if len(a) <= 1:
        r = [doc['_id'] for doc in col.find({'ip': a[0], 'enabled': True})]
    else:
        r = [doc['_id'] for doc in col.find({'ip': a[0], 'port': int(a[1]), 'enabled': True})]

    if len(r) <= 0:
        return str(os.urandom(32).hex())

    return r


# Regex
REGEX_STEAMID = re.compile('(?P<steamid32>(STEAM_)(\\d):(\\d):(\\d+))')
REGEX_STEAM32 = re.compile('(?P<steamid32_actual>(U):(\\d):(\\d+))')
REGEX_STEAM64 = re.compile('(?P<steamid64>(\\d){17})')
REGEX_IDLINK = re.compile('(http(s)?:\\/\\/)?(www\\.)?steamcommunity.com\\/profiles\\/(?P<steamid64>(\\d){17})')
REGEX_CUSTOM_URL = re.compile('(http(s)?:\\/\\/)?(www\\.)?steamcommunity.com\\/id\\/(?P<profile_name>[^\\/]+)')


def wut(gs_id):
    if REGEX_STEAMID.match(gs_id):
        return 'id', REGEX_STEAMID.match(gs_id).groupdict()['steamid']
    elif REGEX_STEAM32.match(gs_id):
        return 'id32', REGEX_STEAM32.match(gs_id).groupdict()['steamid32'][4:]
    elif REGEX_STEAM64.match(gs_id):
        return 'id64', REGEX_STEAM64.match(gs_id).groupdict()['steamid64']
    elif REGEX_IDLINK.match(gs_id):
        return 'id64', REGEX_IDLINK.match(gs_id).groupdict()['steamid64']
    elif REGEX_CUSTOM_URL.match(gs_id):
        return 'custom', REGEX_CUSTOM_URL.match(gs_id).groupdict()['profile_name']
    else:
        return None


async def id64_or_none(app, gs_id):
    a = wut(gs_id)

    if a is not None:
        typ, idt = a
        id64 = None

        if typ == 'custom':
            async with app.state.aio_session.get(f'https://steamcommunity.com/id/{idt}/?xml=1') as resp:
                resp.raise_for_status()

                data = await resp.text()

                a = ElementTree.fromstring(data)
                id64 = a.find('steamID64').text
        elif typ == 'id64':
            id64 = idt
        elif typ == 'id32':
            id64 = str(int(idt) + 76561197960265728)
        else:
            id64 = steamid_to_64(idt)

        if id64 is not None:
            return id64

    return None


def steamid_to_64(steamid):
    n = steamid[6:].split(':')
    y = int(n[1])
    z = int(n[2])
    w = (z * 2) + 0x0110000100000000 + y
    return str(w)


FIELD_MAP = {
    'created': ('created', int),
    'expires': ('expires', int),
    'time_left': ('time_left', int),
    'gs_service': ('user.gs_service', str),
    'gs_id': ('user.gs_id', str),
    'gs_name': ('user.gs_name', str),
    'ip': ('ip', str),
    'admin_id': ('admin', ips_id_to_mongo_object_id),
    'admin': ('admin', admin_name_mongo_ids),
    'server': ('server', server_ip_port_to_mongo_id),
    'reason': ('reason', str),
    'ureason': ('ureason', str),
    # Bitflag fields use a custom type for easier detection
    'is_system': ('flags', 'bitflag', INFRACTION_SYSTEM),
    'is_global': ('flags', 'bitflag', INFRACTION_GLOBAL),
    'is_super_global': ('flags', 'bitflag', INFRACTION_SUPER_GLOBAL),
    'is_permanent': ('flags', 'bitflag', INFRACTION_PERMANENT),
    'is_vpn': ('flags', 'bitflag', INFRACTION_VPN),
    'is_web': ('flags', 'bitflag', INFRACTION_WEB),
    'is_removed': ('flags', 'bitflag', INFRACTION_REMOVED),
    'is_voice': ('flags', 'bitflag', INFRACTION_VOICE_BLOCK),
    'is_text': ('flags', 'bitflag', INFRACTION_CHAT_BLOCK),
    'is_ban': ('flags', 'bitflag', INFRACTION_BAN),
    'is_admin_chat': ('flags', 'bitflag', INFRACTION_ADMIN_CHAT_BLOCK),
    'is_call_admin': ('flags', 'bitflag', INFRACTION_CALL_ADMIN_BAN),
    'is_session': ('flags', 'bitflag', INFRACTION_SESSION)
}


# Parses the input query and converts it into a MongoDB query.
def build_mongo_query(query, include_ip, strict):
    parsed_query = {}
    
    for field, (mongo_field, field_type, *flag_value) in FIELD_MAP.items():
        if field in query:
            if field == 'ip' and not include_ip:
                continue
            if field_type == 'bitflag':
                if parsed_query['flags'] is None:
                    parsed_query['flags'] = {'$bitsAllSet': flag_value}
                else:
                    parsed_query['flags'] = {'$bitsAllSet': parsed_query['flags']['$bitsAllSet'] | flag_value}
            else:
                value_list = query.split(f"{field}:")[-1].split()
                value = ''
                for val in value_list:
                    val = val.strip(' ')
                    if val[0] == '"' and val[len(val) - 1] == '"':
                        value = val.strip('"')
                        break
                if len(value) == 0 or len(value.strip('"')) == 0:
                    continue

                if field == 'gs_name':
                    # Special handling for steam_name - always use $regex to allow for non-exact name matching
                    parsed_query[mongo_field] = {'$regex': re.escape(value), '$options': 'i'}
                else:
                    # Cast to the expected type or call the function on the value
                    value = field_type(value)

                    if mongo_field not in parsed_query:
                        if type(value) == list:
                            parsed_query[mongo_field] = list()
                            parsed_query[mongo_field].append(value) # this is for parsing at end. list in a list means $or check it
                        else:
                            parsed_query[mongo_field] = value
                    elif isinstance(parsed_query[mongo_field], list):
                        parsed_query[mongo_field].append(value)
                    else:
                        parsed_query[mongo_field] = [parsed_query[mongo_field], value] # $and check these later

    to_remove = list()
    and_query = list()

    for key, item in parsed_query.items():
        if isinstance(item, list) and key != '$or' and key != '$and':
            for value in item:
                if type(value) == list:
                    or_query = list()
                    for val in value:
                        or_query.append({key: val})
                    and_query.append({'$or': or_query})
                else:
                    and_query.append({key: value})
            to_remove.append(key)

    if len(and_query) > 0:
        parsed_query['$and'] = and_query
        for key in to_remove:
            del parsed_query[key]

    if len(parsed_query) == 0 and len(query) > 0:
        raise SearchError('No fields in query')
    return parsed_query


def build_plain_text_query(query_string):
    # Fallback to plain text search across multiple fields
    return {
        '$or': [
            {'user.gs_id': {'$regex': re.escape(query_string), '$options': 'i'}},
            {'user.gs_name': {'$regex': re.escape(query_string), '$options': 'i'}},
            {'reason': {'$regex': re.escape(query_string), '$options': 'i'}},
            {'ureason': {'$regex': re.escape(query_string), '$options': 'i'}}
        ]
    }


async def do_infraction_search(app, query: str, include_ip=False, strict=False):
    logger.info(f'XQL: compile and run {query}')

    if len(query) > 2048:
        raise SearchError('Query too long!')

    try:
        compiled_query = build_mongo_query(query, include_ip, strict)
    except Exception as e:
        if strict:
            logger.error('Search failed!', exc_info=e)
            raise SearchError('Query compilation failed') from e

        qs = query.strip(' \t\r\n')

        # Check if we have a steamid
        id64 = await id64_or_none(app, qs)

        if id64 is not None:
            return {'user.gs_service': 'steam', 'user.gs_id': id64}, True

        # Fall back to a plain text search
        return build_plain_text_query(qs), False

    return compiled_query, True


# For VPN whitelist
async def do_whitelist_search(query: str):
    if len(query) > 2048:
        raise SearchError('Query too long!')

    try:
        compiled_query = build_mongo_query(query, include_ip=False, strict=True)
    except Exception as e:
        logger.error('Search failed!', exc_info=e)
        raise SearchError('Query compilation failed') from e

    return compiled_query