from datetime import datetime
from typing import List, Optional, Tuple

from bson import ObjectId
from dateutil.tz import UTC
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import ORJSONResponse
from starlette.requests import Request

from gflbans.api.auth import check_access, csrf_protect
from gflbans.internal.config import MONGO_DB
from gflbans.internal.constants import AUTHED_USER, NOT_AUTHED_USER
from gflbans.internal.database.audit_log import EVENT_EDIT_SERVER, EVENT_NEW_SERVER, DAuditLog
from gflbans.internal.database.server import DServer, DUserIP
from gflbans.internal.flags import PERMISSION_MANAGE_SERVERS
from gflbans.internal.log import logger
from gflbans.internal.models.api import FileInfo, PlayerObj, Server, ServerInternal
from gflbans.internal.models.protocol import AddServer, AddServerReply, EditServer, RegenerateServerTokenReply
from gflbans.internal.utils import generate_api_key

server_router = APIRouter(default_response_class=ORJSONResponse)


def dserver_to_server(dsrv: DServer, indicate_webhooks: bool) -> Server:
    mf = Server(
        id=str(dsrv.id),
        ip=dsrv.ip,
        game_port=dsrv.game_port,
        enabled=dsrv.enabled,
        friendly_name=dsrv.friendly_name,
        online=False,
    )

    if (
        dsrv.server_info is not None
        and (datetime.now(tz=UTC).replace(tzinfo=None) - dsrv.server_info.last_updated).total_seconds() <= 900
    ):
        mf.online = True
        mf.hostname = dsrv.server_info.hostname
        mf.os = dsrv.server_info.os
        mf.player_count = len(dsrv.server_info.players)
        mf.max_players = dsrv.server_info.slot_count
        mf.mod = dsrv.server_info.mod
        mf.map = dsrv.server_info.map
        mf.is_locked = dsrv.server_info.locked

    if indicate_webhooks:
        mf.discord_staff_tag = dsrv.discord_staff_tag
        if getattr(dsrv, 'discord_webhook', None) is not None:
            mf.has_discord_webhook = True
        if getattr(dsrv, 'infract_webhook', None) is not None:
            mf.has_infract_webhook = True

    return mf


def _duserip_to_ply(ply: DUserIP) -> PlayerObj:
    if ply.gs_avatar:
        return PlayerObj(
            gs_service=ply.gs_service,
            gs_id=ply.gs_id,
            gs_name=ply.gs_name,
            gs_avatar=FileInfo(name=ply.gs_avatar.file_name, file_id=ply.gs_avatar.gridfs_file),
        )
    else:
        return PlayerObj(gs_service=ply.gs_service, gs_id=ply.gs_id, gs_name=ply.gs_name)


@server_router.get(
    '/', response_model_exclude_unset=True, response_model_exclude_none=True, response_model=List[Server]
)
async def get_servers(
    request: Request, enabled_only: bool = False, auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)
):
    q = {}

    if enabled_only:
        q['enabled'] = True

    svs = []

    indicate_webhooks = False
    if auth[2] & PERMISSION_MANAGE_SERVERS == PERMISSION_MANAGE_SERVERS:
        indicate_webhooks = True

    async for dsv in DServer.from_query_ex(request.app.state.db[MONGO_DB], q):
        svs.append(dserver_to_server(dsv, indicate_webhooks))

    return svs


@server_router.get(
    '/{server_id}', response_model_exclude_none=True, response_model_exclude_unset=True, response_model=Server
)
async def get_server(
    request: Request, server_id: str, auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)
):
    sv = await DServer.from_id(request.app.state.db[MONGO_DB], server_id)

    if sv is None:
        raise HTTPException(status_code=404, detail='No such server')

    indicate_webhooks = False
    if auth[2] & PERMISSION_MANAGE_SERVERS == PERMISSION_MANAGE_SERVERS:
        indicate_webhooks = True

    return dserver_to_server(sv, indicate_webhooks)


@server_router.get(
    '/{server_id}/players',
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    response_model=List[PlayerObj],
)
async def get_players(request: Request, server_id: str):
    sv = await DServer.from_id(request.app.state.db[MONGO_DB], server_id)

    if sv is None:
        raise HTTPException(detail='Server was not found', status_code=404)

    if (
        sv.server_info is None
        or (datetime.now(tz=UTC).replace(tzinfo=None) - sv.server_info.last_updated).total_seconds() > 900
    ):
        raise HTTPException(detail='Server is offline', status_code=503)

    players = [_duserip_to_ply(ply) for ply in sv.server_info.players]

    return players


@server_router.get(
    '/{server_id}/internal',
    response_model_exclude_none=True,
    response_model_exclude_unset=True,
    response_model=ServerInternal,
)
async def get_server_internal(
    request: Request, server_id: str, auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)
):
    if auth[0] == NOT_AUTHED_USER:
        raise HTTPException(detail='This route requires authentication', status_code=401)

    if auth[2] & PERMISSION_MANAGE_SERVERS != PERMISSION_MANAGE_SERVERS:
        raise HTTPException(detail='You do not have permission to do this!', status_code=403)

    sv = await DServer.from_id(request.app.state.db[MONGO_DB], server_id)

    if sv is None:
        raise HTTPException(detail='Server was not found', status_code=404)

    return ServerInternal(
        id=str(sv.id),
        ip=sv.ip,
        game_port=sv.game_port,
        enabled=sv.enabled,
        friendly_name=sv.friendly_name,
        allow_unknown=sv.allow_unknown,
        discord_staff_tag=sv.discord_staff_tag,
        discord_webhook_set=sv.discord_webhook is not None,
        infract_webhook_set=sv.infract_webhook is not None,
    )


@server_router.post(
    '/',
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    response_model=AddServerReply,
    dependencies=[Depends(csrf_protect)],
)
async def create_server(
    request: Request, n: AddServer, auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)
):
    if auth[0] == NOT_AUTHED_USER:
        raise HTTPException(detail='This route requires authentication', status_code=401)

    if auth[2] & PERMISSION_MANAGE_SERVERS != PERMISSION_MANAGE_SERVERS:
        raise HTTPException(detail='You do not have permission to do this!', status_code=403)

    key, salt, key_hash = generate_api_key()

    dsv = DServer(
        ip=str(n.ip),
        game_port=n.game_port,
        friendly_name=n.friendly_name,
        allow_unknown=n.allow_unknown,
        discord_webhook=n.discord_webhook,
        infract_webhook=n.infract_webhook,
        discord_staff_tag=n.discord_staff_tag,
        server_key=key_hash,
        server_key_salt=salt,
    )

    await dsv.commit(request.app.state.db[MONGO_DB])

    ev_string = f'{auth[0]}/{auth[1]} created a new server with ip {str(n.ip)} and name {dsv.friendly_name}'

    logger.info(ev_string)

    i = auth[1] if auth[1] == AUTHED_USER else None

    await DAuditLog(
        time=datetime.now(tz=UTC),
        event_type=EVENT_NEW_SERVER,
        initiator=i,
        message=ev_string,
        key_pair=(auth[0], auth[1]),
    ).commit(request.app.state.db[MONGO_DB])

    return AddServerReply(
        server_secret_key=key,
        server=ServerInternal(
            id=str(dsv.id),
            ip=dsv.ip,
            game_port=dsv.game_port,
            enabled=dsv.enabled,
            friendly_name=dsv.friendly_name,
            allow_unknown=dsv.allow_unknown,
            discord_webhook_set=dsv.discord_webhook is not None,
            infract_webhook_set=dsv.infract_webhook is not None,
            discord_staff_tag=dsv.discord_staff_tag,
        ),
    )


@server_router.patch(
    '/{server_id}',
    response_model_exclude_none=True,
    response_model_exclude_unset=True,
    response_model=ServerInternal,
    dependencies=[Depends(csrf_protect)],
)
async def edit_server(
    request: Request, e: EditServer, server_id: str, auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)
):
    if auth[0] == NOT_AUTHED_USER:
        raise HTTPException(detail='This route requires authentication', status_code=401)

    if auth[2] & PERMISSION_MANAGE_SERVERS != PERMISSION_MANAGE_SERVERS:
        raise HTTPException(detail='You do not have permission to do this!', status_code=403)

    srv = await DServer.from_id(request.app.state.db[MONGO_DB], server_id)

    if srv is None:
        raise HTTPException(detail='Server does not exist', status_code=404)

    modifications = 'SET'

    if e.ip is not None:
        srv.ip = str(e.ip)
        modifications += f', ip = {srv.ip}'

    if e.game_port is not None:
        srv.game_port = e.game_port
        modifications += f', port = {srv.game_port}'

    if e.enabled is not None:
        srv.enabled = e.enabled
        modifications += f', enabled = {srv.enabled}'

    if e.friendly_name is not None:
        if e.friendly_name == '':
            srv.friendly_name = None
        else:
            srv.friendly_name = e.friendly_name

        modifications += f', friendly_name = {srv.friendly_name}'

    if e.allow_unknown is not None:
        srv.allow_unknown = e.allow_unknown
        modifications += f', enforce_security = {srv.allow_unknown}'

    if e.discord_webhook == '':
        srv.discord_webhook = None
        modifications += ', discord_webhook = None'
    elif e.discord_webhook is not None:
        srv.discord_webhook = e.discord_webhook
        modifications += ', discord_webhook = (CENSORED)'

    if e.infract_webhook == '':
        srv.infract_webhook = None
        modifications += ', infract_webhook = (None)'
    elif e.infract_webhook is not None:
        srv.infract_webhook = e.infract_webhook
        modifications += ', infract_webhook = (CENSORED)'

    if e.discord_webhook == '':
        srv.discord_staff_tag = None
        modifications += ', discord_staff_tag = (None)'
    elif e.discord_staff_tag is not None:
        srv.discord_staff_tag = e.discord_staff_tag
        modifications += f', discord_staff_tag = {srv.discord_staff_tag}'

    if modifications == 'SET':
        raise HTTPException(status_code=400, detail='Request changes nothing')

    await srv.commit(request.app.state.db[MONGO_DB])

    ev_string = f'{auth[0]}/{auth[1]} edited a server {srv.id}'

    logger.info(ev_string)

    i = auth[1] if auth[1] == AUTHED_USER else None

    await DAuditLog(
        time=datetime.now(tz=UTC),
        event_type=EVENT_EDIT_SERVER,
        initiator=i,
        message=ev_string,
        key_pair=(auth[0], auth[1]),
        long_message=modifications,
    ).commit(request.app.state.db[MONGO_DB])

    return ServerInternal(
        id=str(srv.id),
        ip=srv.ip,
        game_port=srv.game_port,
        enabled=srv.enabled,
        friendly_name=srv.friendly_name,
        allow_unknown=srv.allow_unknown,
        discord_webhook_set=srv.discord_webhook is not None,
        infract_webhook_set=srv.infract_webhook is not None,
        discord_staff_tag=srv.discord_staff_tag,
    )


@server_router.get(
    '/{server_id}/token',
    response_model_exclude_none=True,
    response_model_exclude_unset=True,
    response_model=RegenerateServerTokenReply,
    dependencies=[Depends(csrf_protect)],
)
async def regenerate_server_token(
    request: Request, server_id: str, auth: Tuple[int, Optional[ObjectId], int] = Depends(check_access)
):
    if auth[0] == NOT_AUTHED_USER:
        raise HTTPException(detail='This route requires authentication', status_code=401)

    if auth[2] & PERMISSION_MANAGE_SERVERS != PERMISSION_MANAGE_SERVERS:
        raise HTTPException(detail='You do not have permission to do this!', status_code=403)

    srv = await DServer.from_id(request.app.state.db[MONGO_DB], server_id)

    if srv is None:
        raise HTTPException(detail='No such server exists', status_code=404)

    key, salt, key_hash = generate_api_key()
    srv.server_key = key_hash
    srv.server_key_salt = salt

    await srv.commit(request.app.state.db[MONGO_DB])

    ev_string = f'{auth[0]}/{auth[1]} regenerated the server token for {server_id}'

    logger.info(ev_string)

    i = auth[1] if auth[1] == AUTHED_USER else None

    await DAuditLog(
        time=datetime.now(tz=UTC),
        event_type=EVENT_EDIT_SERVER,
        initiator=i,
        message=ev_string,
        key_pair=(auth[0], auth[1]),
    ).commit(request.app.state.db[MONGO_DB])

    return RegenerateServerTokenReply(server_secret_key=key)
