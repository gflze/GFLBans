import asyncio
from asyncio import CancelledError
from datetime import datetime

import bson
import orjson
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import ORJSONResponse
from pytz import UTC
from starlette import status
from starlette.requests import Request
from starlette.responses import Response
from starlette.websockets import WebSocket, WebSocketDisconnect

from gflbans.api.auth import AuthInfo, check_access
from gflbans.internal.config import MONGO_DB
from gflbans.internal.constants import API_KEY, AUTHED_USER, SERVER_KEY
from gflbans.internal.database.audit_log import EVENT_RPC_KICK, DAuditLog
from gflbans.internal.database.rpc import DRPCEventBase, DRPCKickPlayer, add_ack_concern
from gflbans.internal.flags import PERMISSION_RPC_KICK
from gflbans.internal.log import logger
from gflbans.internal.models.protocol import RPCKickRequest
from gflbans.internal.pyapi_utils import get_acting

rpc_router = APIRouter()


@rpc_router.get('/poll')
async def rpc_poll(request: Request, auth: AuthInfo = Depends(check_access)):
    if auth.type != SERVER_KEY:
        raise HTTPException(detail='Only servers may use this route!', status_code=403)

    devs = await DRPCEventBase.poll(request.app.state.db[MONGO_DB], auth.authenticator_id, ack_on_read=True)

    evs = []
    for dev in devs:
        evs.append(dev.as_api().dict())

    return ORJSONResponse(evs, status_code=200)


@rpc_router.websocket('/ws')
async def rpc_ws(websocket: WebSocket):
    if 'Authorization' not in websocket.headers:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    auth = await check_access(websocket, authorization=websocket.headers['Authorization'])

    if auth.type != SERVER_KEY:
        # Only servers can connect to the ws endpoint
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    await websocket.send_json({'api_version': 1})

    async def handle_ack():
        while True:
            try:
                dat = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            try:
                ack_id = ObjectId(dat)
            except bson.errors.InvalidId:
                continue

            try:
                dev_d = await websocket.app.state.db[MONGO_DB].rpc.find_one(ack_id)

                if dev_d is None:
                    continue

                if dev_d['target'] == auth.authenticator_id:
                    await websocket.app.state.db[MONGO_DB].rpc.delete_one({'_id': ack_id})
                else:
                    await websocket.app.state.db[MONGO_DB].rpc.update_one(
                        {'_id': ack_id}, {'$push': {'acknowledged_by': auth.authenticator_id}}
                    )
            except CancelledError:
                raise
            except Exception:
                continue

    asyncio.get_running_loop().create_task(handle_ack())

    while True:
        await asyncio.sleep(1)
        devs = await DRPCEventBase.poll(websocket.app.state.db[MONGO_DB], auth.authenticator_id)

        for dev in devs:
            await websocket.send_text(orjson.dumps(dev.as_api().dict()).decode('utf-8'))


@rpc_router.post('/kick')
async def rpc_kick(request: Request, rpc_kick_req: RPCKickRequest, auth: AuthInfo = Depends(check_access)):
    if auth.type != AUTHED_USER and auth.type != API_KEY:
        raise HTTPException(status_code=403, detail='Bad key type')

    if auth.permissions & PERMISSION_RPC_KICK != PERMISSION_RPC_KICK:
        raise HTTPException(status_code=403, detail='You do not have permission to do this!')

    acting_admin, _ = await get_acting(request, None, auth.type, auth.authenticator_id)

    logger.info(
        f'{acting_admin.name} ({acting_admin.ips_id}) kicked '
        f'{rpc_kick_req.player.gs_service}/{rpc_kick_req.player.gs_id} from {rpc_kick_req.server_id}'
    )

    await DAuditLog(
        time=datetime.now(tz=UTC).timestamp(),
        event_type=EVENT_RPC_KICK,
        authentication_type=auth.type,
        authenticator=auth.authenticator_id,
        admin=auth.admin.mongo_admin_id if auth.admin else None,
        new_item=rpc_kick_req.player.dict(),
    ).commit(request.app.state.db[MONGO_DB])

    drpc = DRPCKickPlayer(
        time=datetime.now(tz=UTC), target=ObjectId(rpc_kick_req.server_id), target_player=rpc_kick_req.player
    )

    await drpc.commit(request.app.state.db[MONGO_DB])

    try:
        await asyncio.wait_for(add_ack_concern(request.app.state.db[MONGO_DB], drpc.id), timeout=15)
    except asyncio.TimeoutError:
        return Response(status_code=504)

    # The server is supposed to send a heartbeat immediately after responding to the RPC kick
    # This will give the server 5 seconds to have sent the heartbeat
    # This is mainly to prevent confusion on the front end (i.e. I just kicked this person, why are they here?)
    await asyncio.sleep(5)

    return Response(status_code=204)
