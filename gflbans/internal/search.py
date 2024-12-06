import os
import re
from concurrent.futures.process import ProcessPoolExecutor
from typing import Any, Dict

from bson import ObjectId
from pymongo import MongoClient

from defusedxml import ElementTree

from gflbans.internal.config import MONGO_URI, MONGO_DB
from gflbans.internal.errors import SearchError
from gflbans.internal.flags import INFRACTION_DEC_ONLINE_ONLY, INFRACTION_SYSTEM, INFRACTION_PERMANENT, INFRACTION_SUPER_GLOBAL, INFRACTION_GLOBAL, \
    INFRACTION_VPN, INFRACTION_WEB, INFRACTION_REMOVED, INFRACTION_VOICE_BLOCK, INFRACTION_CHAT_BLOCK, INFRACTION_BAN, \
    INFRACTION_ADMIN_CHAT_BLOCK, INFRACTION_CALL_ADMIN_BAN, INFRACTION_SESSION
from gflbans.internal.integrations.ips import ips_get_member_id_from_gsid
from gflbans.internal.log import logger
from gflbans.internal.models.protocol import Search

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

# Find admins given a generic steam id
def steam_id_to_mongo_object_id(steam_id: str):
    steam_id_type = wut(steam_id)

    if steam_id_type is None:
        raise SearchError('Invalid admin Steam ID')

    typ, idt = steam_id_type

    ips_id = None
    if typ == 'id':
        ips_id = ips_get_member_id_from_gsid(steamid_to_64(idt))
    elif typ == 'id64':
        ips_id = ips_get_member_id_from_gsid(idt)
    elif typ == 'id32':
        ips_id = int(idt)

    if ips_id is None:
        raise SearchError('Invalid admin Steam ID type')
    
    return ips_id_to_mongo_object_id(ips_id)


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
REGEX_STEAMID = re.compile('(?P<steamid>(STEAM_)(\\d):(\\d):(\\d+))')
REGEX_STEAM32 = re.compile('(?P<steamid32>(U):(\\d):(\\d+))')
REGEX_STEAM64 = re.compile('(?P<steamid64>(\\d){17})')
REGEX_IDLINK = re.compile('(http(s)?:\\/\\/)?(www\\.)?steamcommunity.com\\/profiles\\/(?P<steamid64>(\\d){17})')
REGEX_CUSTOM_URL = re.compile('(http(s)?:\\/\\/)?(www\\.)?steamcommunity.com\\/id\\/(?P<profile_name>[^\\/]+)')
REGEX_IS_NUMBER = re.compile('(\\d){17}')


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
    elif gs_id.isdigit() and len(str(int(gs_id) + 76561197960265728)) == 17:
        return 'id32', ips_get_member_id_from_gsid(int(gs_id) + 76561197960265728)
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
        elif typ == 'id':
            id64 = steamid_to_64(idt)

        if id64 is not None:
            return id64

    return None

def id64_or_none_no_web(gs_id):
    steam_id_type = wut(gs_id)

    if steam_id_type is None:
        raise SearchError('Invalid Steam ID')

    typ, idt = steam_id_type

    if typ == 'id':
        return steamid_to_64(idt)
    elif typ == 'id64':
        return idt
    elif typ == 'id32':
        return str(int(idt) + 76561197960265728)

    raise SearchError('Invalid Steam ID type')
    

def steamid_to_64(steamid):
    n = steamid[6:].split(':')
    y = int(n[1])
    z = int(n[2])
    w = (z * 2) + 0x0110000100000000 + y
    return str(w)


FIELD_MAP = {
    'gs_service': ('user.gs_service', str),
    'gs_id': ('user.gs_id', id64_or_none_no_web),
    'gs_name': ('user.gs_name', str),
    'ip': ('ip', str),
    'admin_id': ('admin', steam_id_to_mongo_object_id),
    'admin': ('admin', admin_name_mongo_ids),
    'server': ('server', ObjectId),
    'reason': ('reason', str),
    'ureason': ('ureason', str),
    # 'is_active': (),
    # 'is_expired': (),
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
    'is_session': ('flags', 'bitflag', INFRACTION_SESSION),
    'is_decl_online_only': ('flags', 'bitflag', INFRACTION_DEC_ONLINE_ONLY)

    # NOT Bitflags
    # 'is_server': ('flags', 'notBitflag', INFRACTION_GLOBAL | INFRACTION_SUPER_GLOBAL),
    # 'is_warning': ('flags', 'notBitflag', INFRACTION_VOICE_BLOCK | INFRACTION_CHAT_BLOCK | INFRACTION_BAN | INFRACTION_ADMIN_CHAT_BLOCK | INFRACTION_CALL_ADMIN_BAN)
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

async def do_infraction_search(app, query: Search, include_ip: bool = False) -> Dict[str, Any]:
    logger.info(f"Performing search with: {query}")
    
    parsed_query = {}
    if query.search:
        if len(query.search) > 2048:
            raise SearchError('Search too long!')
        qs = query.search.strip(' \t\r\n')

        # Check if we have a steamid
        id64 = id64_or_none(app, qs)
        if id64 is not None:
            parsed_query = {'user.gs_service': 'steam', 'user.gs_id': id64}

        # Fall back to a plain text search
        parsed_query = build_plain_text_query(qs)

    for field, (mongo_field, field_type, *flag_value) in FIELD_MAP.items():
        value = getattr(query, field, None)

        if value is None:
            continue

        if field == 'ip' and not include_ip:
            continue

        if field_type == 'bitflag':
            if 'flags' not in parsed_query:
                parsed_query['flags'] = {'$bitsAllSet': 0}
            parsed_query['flags']['$bitsAllSet'] |= flag_value[0]
        elif callable(field_type) and field == 'admin':
            possible_admin_ids = admin_name_mongo_ids(value)
            parsed_query['$or'] = [
                {mongo_field: admin_id} for admin_id in possible_admin_ids
            ]
        else:
            if isinstance(value, str) and mongo_field == 'user.gs_name':
                parsed_query[mongo_field] = {'$regex': re.escape(value), '$options': 'i'}
            else:
                parsed_query[mongo_field] = field_type(value)

    # Handle comparison modes
    for field, comparison_field in [
        ("created", "created_comparison_mode"),
        ("expires", "expires_comparison_mode"),
        ("time_left", "time_left_comparison_mode"),
        ("duration", "duration_comparison_mode"),
    ]:
        value = getattr(query, field, None)
        comparison_mode = getattr(query, comparison_field, None)

        if value is not None and comparison_mode in {"=", "<", "<=", ">", ">="}:
            mongo_comparison = {"=": "$eq","<": "$lt", "<=": "$lte", ">": "$gt", ">=": "$gte"}[comparison_mode]
            parsed_query[field] = {mongo_comparison: value}

    return parsed_query


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