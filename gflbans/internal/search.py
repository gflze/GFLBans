import os
import re
import time
from concurrent.futures.process import ProcessPoolExecutor
from typing import Any, Dict

from bson import ObjectId
from defusedxml import ElementTree
from pymongo import MongoClient

from gflbans.internal.config import MONGO_DB, MONGO_URI
from gflbans.internal.errors import SearchError
from gflbans.internal.flags import (
    INFRACTION_ADMIN_CHAT_BLOCK,
    INFRACTION_BAN,
    INFRACTION_CALL_ADMIN_BAN,
    INFRACTION_CHAT_BLOCK,
    INFRACTION_GLOBAL,
    INFRACTION_ITEM_BLOCK,
    INFRACTION_PERMANENT,
    INFRACTION_PLAYTIME_DURATION,
    INFRACTION_REMOVED,
    INFRACTION_SESSION,
    INFRACTION_SYSTEM,
    INFRACTION_VOICE_BLOCK,
    INFRACTION_VPN,
    INFRACTION_WEB,
)
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


def contains_str(s: str):
    return {'$regex': re.escape(s), '$options': 'i'}


async def plaintext_search(app, s: str):
    if len(s) > 2048:
        raise SearchError('Search too long!')
    qs = s.strip(' \t\r\n')

    id64 = await id64_or_none(app, qs)
    if id64 is not None:
        return {'user.gs_service': 'steam', 'user.gs_id': id64}
    else:
        return build_plain_text_query(qs)


def build_plain_text_query(query_string):
    search = contains_str(query_string)
    # Fallback to plain text search across multiple fields
    return {'$or': [{'user.gs_id': search}, {'user.gs_name': search}, {'reason': search}, {'ureason': search}]}


def player_name_check(app, s: str):
    return {'user.gs_name': {'$regex': re.escape(s), '$options': 'i'}}


async def admin_name_to_mongo_ids(app, s: str):
    client = MongoClient(MONGO_URI)
    col = client[MONGO_DB].admin_cache

    r = [doc['_id'] for doc in col.find({'name': {'$regex': s, '$options': 'i'}})]

    if len(r) <= 0:
        return str(os.urandom(32).hex())

    return {'$or': [{'admin': admin_id} for admin_id in r]}


async def expiration_check(app, b: bool):
    if b:
        return {
            '$and': [
                {'flags': {'$bitsAllClear': INFRACTION_REMOVED}},
                {
                    '$or': [
                        {'$and': [{'expires': {'$exists': True}}, {'expires': {'$lte': time.time()}}]},
                        {'$and': [{'time_left': {'$exists': True}}, {'time_left': 0}]},
                        {'flags': {'$bitsAnySet': INFRACTION_SESSION}},
                    ]
                },
            ]
        }
    else:
        return {
            '$and': [
                {'$or': [{'expires': {'$exists': False}}, {'expires': {'$gt': time.time()}}]},
                {'$or': [{'time_left': {'$exists': False}}, {'time_left': {'$gt': 0}}]},
                {'flags': {'$bitsAllClear': INFRACTION_SESSION | INFRACTION_REMOVED}},
            ]
        }


async def active_check(app, b: bool):
    if b:
        return {
            '$and': [
                {'$or': [{'expires': {'$exists': False}}, {'expires': {'$gt': time.time()}}]},
                {'$or': [{'time_left': {'$exists': False}}, {'time_left': {'$gt': 0}}]},
                {'flags': {'$bitsAllClear': INFRACTION_SESSION | INFRACTION_REMOVED}},
            ]
        }
    else:
        return {
            '$or': [
                {'$and': [{'expires': {'$exists': True}}, {'expires': {'$lte': time.time()}}]},
                {'$and': [{'time_left': {'$exists': True}}, {'time_left': 0}]},
                {'flags': {'$bitsAnySet': INFRACTION_SESSION | INFRACTION_REMOVED}},
            ]
        }


FIELD_MAP = {
    # Checks single mongodb document field
    'gs_service': ('user.gs_service', str),
    'gs_id': ('user.gs_id', id64_or_none_no_web),
    'gs_name': ('user.gs_name', contains_str),
    'ip': ('ip', str),
    'admin_id': ('admin', steam_id_to_mongo_object_id),
    'server': ('server', ObjectId),
    'reason': ('reason', contains_str),
    'ureason': ('ureason', contains_str),
    # Complex checks that can't simply be a value assigned to a key
    'search': ('computed', str, plaintext_search),
    'admin': ('computed', str, admin_name_to_mongo_ids),
    'is_expired': ('computed', bool, expiration_check),
    'is_active': ('computed', bool, active_check),
    # Bitflag checks for 'flags' field in mongodb documents
    'is_system': ('bitflag', bool, INFRACTION_SYSTEM),
    'is_global': ('bitflag', bool, INFRACTION_GLOBAL),
    'is_permanent': ('bitflag', bool, INFRACTION_PERMANENT),
    'is_vpn': ('bitflag', bool, INFRACTION_VPN),
    'is_web': ('bitflag', bool, INFRACTION_WEB),
    'is_removed': ('bitflag', bool, INFRACTION_REMOVED),
    'is_voice': ('bitflag', bool, INFRACTION_VOICE_BLOCK),
    'is_text': ('bitflag', bool, INFRACTION_CHAT_BLOCK),
    'is_ban': ('bitflag', bool, INFRACTION_BAN),
    'is_admin_chat': ('bitflag', bool, INFRACTION_ADMIN_CHAT_BLOCK),
    'is_call_admin': ('bitflag', bool, INFRACTION_CALL_ADMIN_BAN),
    'is_item': ('bitflag', bool, INFRACTION_ITEM_BLOCK),
    'is_session': ('bitflag', bool, INFRACTION_SESSION),
    'is_playtime_duration': ('bitflag', bool, INFRACTION_PLAYTIME_DURATION),
}


async def do_infraction_search(app, query: Search, include_ip: bool = False) -> Dict[str, Any]:
    logger.info(f'Performing search with: {query}')

    parsed_query = []
    set_bit_flags = 0
    unset_bit_flags = 0

    for field, (mongo_field, field_type, *special) in FIELD_MAP.items():
        value = getattr(query, field, None)

        if not include_ip and field == 'ip' and value is not None:
            raise SearchError('Cannot search by IP without proper permissions.')

        if value is None or not (callable(field_type) or isinstance(value, field_type)):
            continue

        if mongo_field == 'bitflag':
            if value:
                set_bit_flags |= special[0]
            else:
                unset_bit_flags |= special[0]
        elif mongo_field == 'computed':
            parsed_query.append(await special[0](app, value))
        else:
            parsed_query.append({mongo_field: field_type(value)})

    # Handle comparisons for time based searches
    for field, comparison_field in [
        ('created', 'created_comparison_mode'),
        ('expires', 'expires_comparison_mode'),
        ('time_left', 'time_left_comparison_mode'),
        ('duration', 'duration_comparison_mode'),
    ]:
        value = getattr(query, field, None)
        comparison_mode = getattr(query, comparison_field, None)

        if value is not None and isinstance(value, int) and comparison_mode in {'eq', 'lt', 'lte', 'gt', 'gte'}:
            if field != 'created':
                unset_bit_flags |= INFRACTION_PERMANENT | INFRACTION_SESSION
            mongo_comparison = {'eq': '$eq', 'lt': '$lt', 'lte': '$lte', 'gt': '$gt', 'gte': '$gte'}[comparison_mode]
            if field == 'duration':
                if comparison_mode == 'eq':
                    tolerance = 30  # tolerance in seconds for floating point calculation imprecision in equivalancy
                    duration_query = {
                        '$or': [
                            {
                                '$and': [
                                    {'original_time': {'$exists': True}},
                                    {'original_time': {'$gte': (value - tolerance)}},
                                    {'original_time': {'$lte': (value + tolerance)}},
                                ]
                            },
                            {
                                '$and': [
                                    {'expires': {'$exists': True}},
                                    {
                                        '$expr': {
                                            '$and': [
                                                {
                                                    '$gte': [
                                                        {'$round': [{'$subtract': ['$expires', '$created']}, 0]},
                                                        value - tolerance,
                                                    ]
                                                },
                                                {
                                                    '$lte': [
                                                        {'$round': [{'$subtract': ['$expires', '$created']}, 0]},
                                                        value + tolerance,
                                                    ]
                                                },
                                            ]
                                        }
                                    },
                                ]
                            },
                        ]
                    }
                else:
                    duration_query = {
                        '$or': [
                            {'original_time': {mongo_comparison: value}},
                            {
                                '$and': [
                                    {'expires': {'$exists': True}},
                                    {
                                        '$expr': {
                                            mongo_comparison: [
                                                {'$round': [{'$subtract': ['$expires', '$created']}, 0]},
                                                value,
                                            ]
                                        }
                                    },
                                ]
                            },
                        ]
                    }
                    if comparison_mode in {'gt', 'gte'}:
                        unset_bit_flags = INFRACTION_SESSION
                        duration_query = {
                            '$or': [
                                duration_query,
                                {'flags': {'$bitsAllSet': INFRACTION_PERMANENT}},
                            ]
                        }
                    elif comparison_mode in {'lt', 'lte'}:
                        unset_bit_flags = INFRACTION_PERMANENT
                        duration_query = {
                            '$or': [
                                duration_query,
                                {'flags': {'$bitsAllSet': INFRACTION_SESSION}},
                            ]
                        }
                parsed_query.append(duration_query)
            elif comparison_mode == 'eq' and (field == 'created' or field == 'expires'):
                parsed_query.append({field: {'$gte': value, '$lte': value + 24 * 60 * 60}})
            else:
                if 'gt' in comparison_mode and (field == 'created' or field == 'expires'):
                    value += 24 * 60 * 60
                parsed_query.append({field: {mongo_comparison: value}})

    if set_bit_flags > 0 and unset_bit_flags > 0:
        parsed_query.append({'flags': {'$bitsAllSet': set_bit_flags, '$bitsAllClear': unset_bit_flags}})
    elif set_bit_flags > 0:
        parsed_query.append({'flags': {'$bitsAllSet': set_bit_flags}})
    elif unset_bit_flags > 0:
        parsed_query.append({'flags': {'$bitsAllClear': unset_bit_flags}})

    if not parsed_query:
        return {}
    else:
        return {'$and': parsed_query}
