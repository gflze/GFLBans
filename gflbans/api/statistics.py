import asyncio
from contextlib import suppress
from datetime import datetime, time, timedelta

from redis.exceptions import RedisError
from dateutil.tz import UTC
from fastapi import APIRouter
from fastapi.responses import ORJSONResponse
from starlette.requests import Request

from gflbans.internal.config import MONGO_DB
from gflbans.internal.database.infraction import DInfraction
from gflbans.internal.database.server import DServer
from gflbans.internal.flags import INFRACTION_REMOVED, INFRACTION_PERMANENT, INFRACTION_CALL_ADMIN_BAN, \
    INFRACTION_ADMIN_CHAT_BLOCK, INFRACTION_BAN, INFRACTION_CHAT_BLOCK, INFRACTION_VOICE_BLOCK
from gflbans.internal.models.api import InfractionDay
from gflbans.internal.models.protocol import ServerStats

statistics_router = APIRouter(default_response_class=ORJSONResponse)


@statistics_router.get('/', response_model=ServerStats, response_model_exclude_defaults=False,
                       response_model_exclude_unset=False)
async def generate_statistics(request: Request):
    with suppress(RedisError):
        a = await request.app.state.cache.get('HOME_PAGE_STATS', 'graph_cache')
        if a is not None:
            return ServerStats(**a)

    qs = [
        request.app.state.db[MONGO_DB].infractions.count_documents({}),
        request.app.state.db[MONGO_DB].infractions.count_documents({'$and': [
            {'flags': {'$bitsAllClear': INFRACTION_REMOVED}},
            {'$or': [
                {'time_left': {'$gt': 0}},
                {'expires': {'$gt': datetime.now(tz=UTC).timestamp()}},
                {'flags': {'$bitsAllSet': INFRACTION_PERMANENT}}
            ]}
        ]}),
        request.app.state.db[MONGO_DB].servers.count_documents({'enabled': True}),
        request.app.state.db[MONGO_DB].infractions.count_documents({'flags': {'$bitsAllSet': INFRACTION_VOICE_BLOCK}}),
        request.app.state.db[MONGO_DB].infractions.count_documents({'flags': {'$bitsAllSet': INFRACTION_CHAT_BLOCK}}),
        request.app.state.db[MONGO_DB].infractions.count_documents({'flags': {'$bitsAllSet': INFRACTION_BAN}}),
        request.app.state.db[MONGO_DB].infractions.count_documents({'flags': {'$bitsAllClear':
                                                                                INFRACTION_VOICE_BLOCK |
                                                                                INFRACTION_CHAT_BLOCK |
                                                                                INFRACTION_BAN |
                                                                                INFRACTION_ADMIN_CHAT_BLOCK |
                                                                                INFRACTION_CALL_ADMIN_BAN}}),

    ]

    r = await asyncio.gather(*qs)

    pc = 0

    async for doc in DServer.from_query_ex(request.app.state.db[MONGO_DB], {'enabled': True}):
        if doc.server_info is not None and (datetime.now(tz=UTC).replace(tzinfo=None) - doc.server_info.last_updated) \
                .total_seconds() < 900:
            pc += len(doc.server_info.players)

    hist = {}

    dt = int((datetime.combine(datetime.today(), time.min) - timedelta(days=7)).astimezone(tz=UTC).timestamp())

    for dr in range(7):
        dx = (datetime.combine(datetime.today(), time.min) - timedelta(days=dr + 1)).strftime('%Y/%m/%d')
        hist[dx] = InfractionDay()

    async for doc in DInfraction.from_query(request.app.state.db[MONGO_DB], {'created': {'$gte': dt}}):
        dt = datetime.fromtimestamp(doc.created, tz=UTC)
        dk = dt.strftime('%Y/%m/%d')

        if dk not in hist:
            hist[dk] = InfractionDay()

        hist[dk].total += 1

        if doc.flags & INFRACTION_BAN == INFRACTION_BAN:
            hist[dk].bans += 1

        if doc.flags & INFRACTION_VOICE_BLOCK == INFRACTION_VOICE_BLOCK:
            hist[dk].voice_blocks += 1

        if doc.flags & INFRACTION_CHAT_BLOCK == INFRACTION_CHAT_BLOCK:
            hist[dk].chat_blocks += 1

        if doc.flags & INFRACTION_ADMIN_CHAT_BLOCK == INFRACTION_ADMIN_CHAT_BLOCK:
            hist[dk].admin_chat_blocks += 1

        if doc.flags & INFRACTION_CALL_ADMIN_BAN == INFRACTION_CALL_ADMIN_BAN:
            hist[dk].call_admin_blocks += 1

        af = INFRACTION_BAN | INFRACTION_VOICE_BLOCK | INFRACTION_CHAT_BLOCK | INFRACTION_ADMIN_CHAT_BLOCK | INFRACTION_CALL_ADMIN_BAN

        if doc.flags & af == 0:
            hist[dk].warnings += 1

    result = ServerStats(total_infractions=r[0],
                         active_infractions=r[1],
                         total_servers=r[2],
                         online_players=pc,
                         total_voice_blocks=r[3],
                         total_chat_blocks=r[4],
                         total_bans=r[5],
                         total_warnings=r[6],
                         history=hist)

    with suppress(RedisError):
        await request.app.state.cache.set('HOME_PAGE_STATS', result.dict(), 'graph_cache', expire_time=3600)

    return result
