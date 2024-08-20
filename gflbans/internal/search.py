import asyncio
import os
import re
from concurrent.futures.process import ProcessPoolExecutor
from functools import partial

from pymongo import MongoClient

from xql import xql_compile
from xql.compilers.XqlMongoCompiler import XqlMongoCompiler
from defusedxml import ElementTree

from xql.model import XqlModel, XqlString, XqlBoolBit, XqlInteger

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
    col = db.admins

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


class InfractionSearchModel(XqlModel):
    created = XqlInteger(backend_field='created')
    expires = XqlInteger(backend_field='expires')
    time_left = XqlInteger(backend_field='time_left')
    gs_service = XqlString(backend_field='user.gs_service')
    gs_id = XqlString(backend_field='user.gs_id')
    gs_name = XqlString(backend_field='user.gs_name')
    admin_id = XqlString(backend_field='admin', cast=ips_id_to_mongo_object_id)
    admin = XqlString(backend_field='admin', cast=admin_name_mongo_ids)
    server = XqlString(backend_field='server', cast=server_ip_port_to_mongo_id)
    reason = XqlString(backend_field='reason')
    ureason = XqlString(backend_field='ureason')

    # BoolBits
    is_system = XqlBoolBit(backend_field='flags', b=INFRACTION_SYSTEM)
    is_global = XqlBoolBit(backend_field='flags', b=INFRACTION_GLOBAL)
    is_super_global = XqlBoolBit(backend_field='flags', b=INFRACTION_SUPER_GLOBAL)
    is_permanent = XqlBoolBit(backend_field='flags', b=INFRACTION_PERMANENT)
    is_vpn = XqlBoolBit(backend_field='flags', b=INFRACTION_VPN)
    is_web = XqlBoolBit(backend_field='flags', b=INFRACTION_WEB)
    is_removed = XqlBoolBit(backend_field='flags', b=INFRACTION_REMOVED)
    is_voice = XqlBoolBit(backend_field='flags', b=INFRACTION_VOICE_BLOCK)
    is_text = XqlBoolBit(backend_field='flags', b=INFRACTION_CHAT_BLOCK)
    is_ban = XqlBoolBit(backend_field='flags', b=INFRACTION_BAN)
    is_admin_chat = XqlBoolBit(backend_field='flags', b=INFRACTION_ADMIN_CHAT_BLOCK)
    is_call_admin = XqlBoolBit(backend_field='flags', b=INFRACTION_CALL_ADMIN_BAN)
    is_session = XqlBoolBit(backend_field='flags', b=INFRACTION_SESSION)


class WhitelistAdminSearchModel(XqlModel):
    name = XqlString(backend_field='name')
    ips_id = XqlInteger(backend_field='ips_user')


# Only some users can search by ip
class InfractionSearchModelIP(InfractionSearchModel):
    ip = XqlString(backend_field='ip')


# Regex
REGEX_STEAM32 = re.compile('(?P<steamid32>(STEAM_)(\\d):(\\d):(\\d+))')
REGEX_STEAM32_ACTUAL = re.compile('(?P<steamid32_actual>(U):(\\d):(\\d+))')
REGEX_STEAM64 = re.compile('(?P<steamid64>(\\d){17})')
REGEX_IDLINK = re.compile('(http(s)?:\\/\\/)?(www\\.)?steamcommunity.com\\/profiles\\/(?P<steamid64>(\\d){17})')
REGEX_CUSTOM_URL = re.compile('(http(s)?:\\/\\/)?(www\\.)?steamcommunity.com\\/id\\/(?P<profile_name>[^\\/]+)')


def wut(gs_id):
    if REGEX_STEAM32.match(gs_id):
        return 'id32', REGEX_STEAM32.match(gs_id).groupdict()['steamid32']
    elif REGEX_STEAM32_ACTUAL.match(gs_id):
        return 'id32_actual', REGEX_STEAM32_ACTUAL.match(gs_id).groupdict()['steamid32_actual'][4:]
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
        elif typ == 'id32_actual':
            id64 = str(int(idt) + 76561197960265728)
        else:
            id64 = steamid32_to_64(idt)

        if id64 is not None:
            return id64

    return None


def steamid32_to_64(id32):
    n = id32[6:].split(':')
    y = int(n[1])
    z = int(n[2])
    w = (z * 2) + 0x0110000100000000 + y
    return str(w)


async def do_infraction_search(app, query: str, include_ip=False, strict=False):

    c = True

    logger.info(f'XQL: compile and run {query}')

    if include_ip:
        model = InfractionSearchModelIP
    else:
        model = InfractionSearchModel

    if len(query) > 2048:
        raise SearchError('Query too long!')

    loop = asyncio.get_running_loop()

    try:
        compiled_query = await asyncio.wait_for(
            loop.run_in_executor(executor, partial(xql_compile, target=XqlMongoCompiler(model()), query=query)),
            timeout=20)
    except asyncio.TimeoutError as e:
        logger.info(f'XQL: Query compiler took too long! Query = {query}', exc_info=True)
        raise SearchError('Query took to long to compile. Try again later') from e
    except Exception as e:

        if strict:
            logger.error('XQL: Search failed!', exc_info=e)
            raise SearchError('Query compilation failed') from e

        qs = query.strip(' \t\r\n')

        # Check if we have a steamid
        id64 = await id64_or_none(app, qs)

        if id64 is not None:
            return {'user.gs_service': 'steam', 'user.gs_id': id64}, True

        # Fall back to a pain text search
        c = False

        compiled_query = {
            '$or': [
                {'user.gs_service': {'$regex': re.escape(qs), '$options': 'i'}},
                {'user.gs_id': {'$regex': re.escape(qs), '$options': 'i'}},
                {'user.gs_name': {'$regex': re.escape(qs), '$options': 'i'}},
                {'reason': {'$regex': re.escape(qs), '$options': 'i'}},
                {'ureason': {'$regex': re.escape(qs), '$options': 'i'}}
            ]
        }

    return compiled_query, c


async def do_whitelist_search(query: str):
    if len(query) > 2048:
        raise SearchError('Query too long!')

    loop = asyncio.get_running_loop()

    try:
        compiled_query = await asyncio.wait_for(
            loop.run_in_executor(executor, partial(xql_compile, target=XqlMongoCompiler(WhitelistAdminSearchModel()),
                                                   query=query)), timeout=20)
    except asyncio.TimeoutError as e:
        logger.info(f'XQL: Query compiler took too long! Query = {query}', exc_info=True)
        raise SearchError('Query took to long to compile. Try again later') from e
    except Exception as e:
        logger.error('XQL: Search failed!', exc_info=e)
        raise SearchError('Query compilation failed') from e

    return compiled_query
