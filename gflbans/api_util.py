import html
from contextlib import suppress
from datetime import datetime
from typing import List, Optional

import bbcode
from aredis import RedisError
from bson import ObjectId
from dateutil.tz import UTC
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from starlette.requests import Request

from gflbans.internal.config import MONGO_DB
from gflbans.internal.constants import NOT_AUTHED_USER
from gflbans.internal.database.common import DFile
from gflbans.internal.database.infraction import DComment, DUser, DInfraction
from gflbans.internal.flags import PERMISSION_VIEW_IP_ADDR, INFRACTION_PERMANENT, INFRACTION_DEC_ONLINE_ONLY, \
    INFRACTION_SESSION, str2pflag
from gflbans.internal.models.api import Comment, FileInfo, PlayerObjSimple, PlayerObj, Infraction, CInfractionSummary
from gflbans.internal.models.protocol import CheckInfractionsReply
from gflbans.internal.utils import validate


async def admin_as_int(app, a: Optional[ObjectId]):
    if a is None:
        return None

    with suppress(RedisError):
        admin = await app.state.cache.get(str(a), 'admin_id_cache')

        if admin:
            return admin['ips_user']

    admin = await app.state.db[MONGO_DB].admin_cache.find_one({'_id': a})

    if admin is not None:
        with suppress(RedisError):
            await app.state.cache.set(str(a), {'ips_user': admin['ips_user']}, 'admin_id_cache', expire_time=3600)

        return admin['ips_user']

    return None


async def find_admin_name(db_ref: AsyncIOMotorDatabase, a: Optional[ObjectId]):
    if a is None:
        return 'SYSTEM'

    admin = await db_ref.admin_cache.find_one({'_id': a})

    if admin is None:
        return 'SYSTEM'

    an = admin['name'] if 'name' in admin else 'SYSTEM'
    return an


def as_edict(ed):
    a = {}

    if 'time' in ed:
        a = {'time': ed['time']}

    if 'admin' in ed:
        a['admin'] = str_id(ed['admin'])

    return a


def render_comment(comment: str):
    bbparser = bbcode.Parser()

    # I only really want urls atm until i can unfuck the formatting

    with suppress(KeyError):
        ttk = set()

        for tag in bbparser.recognized_tags:
            if tag != 'url':
                ttk.add(tag)

        for tag in ttk:
            del bbparser.recognized_tags[tag]

    return bbparser.format(comment)


def to_unix(dt: datetime):
    if dt is not None:
        return int(dt.replace(tzinfo=UTC).timestamp())
    else:
        return 0


async def as_comment(app, c: DComment) -> Comment:
    return Comment(edit_data=as_edict(c.edit_data), author=await admin_as_int(app, c.author), content=c.content,
                   private=c.private, rendered=render_comment(c.content), created=to_unix(c.created))


async def as_comments(app, c: List[DComment], exclude_priv=True) -> List[Comment]:
    c2 = []

    for com in c:
        if exclude_priv and com.private:
            continue

        c2.append(await as_comment(app, com))

    return c2


async def as_files(app, f: List[DFile], exclude_priv=True) -> List[FileInfo]:
    e = []

    for df in f:
        if exclude_priv and df.private:
            continue

        fi = FileInfo(file_id=df.gridfs_file, name=df.file_name, uploaded_by=await admin_as_int(app, df.uploaded_by),
                      private=df.private)

        if df.created:
            fi.created = int(df.created.replace(tzinfo=UTC).timestamp())

        fi.rendered = '<em>Attached a file: <a href="%s">%s</a></em>' \
                      % (html.escape(f'/file/uploads/{df.gridfs_file}/{df.file_name}', True),
                         html.escape(f'{df.file_name}', True))

        e.append(fi)

    return e


def as_player_simple(user: Optional[DUser], ip: Optional[str], include_ip: bool = True):
    if user is not None and ip is None:
        return PlayerObjSimple(gs_service=user.gs_service, gs_id=user.gs_id)
    elif user is None and ip is not None:
        if include_ip:
            return PlayerObjSimple(ip=ip)
        else:
            return PlayerObjSimple(ip='MISSING_PERMISSIONS')
    elif user is not None and ip is not None:
        pobj = PlayerObjSimple(gs_service=user.gs_service, gs_id=user.gs_id)

        if include_ip:
            pobj.ip = ip

        return pobj
    else:
        raise ValueError('Bad database object! Missing both an ip and a user')


def as_file_info(df: Optional[DFile]):
    if df is None:
        return None

    return FileInfo(file_id=df.gridfs_file, name=df.file_name)


def as_player(user: Optional[DUser], ip: Optional[str], include_ip: bool = True):
    pos = as_player_simple(user, ip, include_ip)
    pf = {}

    if user is not None:
        if user.gs_name is not None:
            pf['gs_name'] = user.gs_name

        if user.gs_avatar is not None:
            pf['gs_avatar'] = as_file_info(user.gs_avatar).dict()

    return PlayerObj(**pos.dict(), **pf)


async def as_infraction(app, infraction: DInfraction, include_ip=True) -> Infraction:
    return Infraction(id=str_id(infraction.id),
                      flags=infraction.flags,
                      comments=await as_comments(app, infraction.comments, exclude_priv=not include_ip),
                      files=await as_files(app, infraction.files, exclude_priv=not include_ip),
                      server=str_id(infraction.server),
                      created=infraction.created,
                      expires=infraction.expires,
                      player=as_player(infraction.user, infraction.ip, include_ip),
                      admin=await admin_as_int(app, infraction.admin),
                      reason=infraction.reason,
                      removed_on=infraction.removed,
                      removed_by=await admin_as_int(app, infraction.remover),
                      removal_reason=infraction.ureason,
                      time_left=infraction.time_left,
                      orig_length=infraction.original_time,
                      policy_id=str_id(infraction.policy_id),
                      last_heartbeat=infraction.last_heartbeat)


def str_id(o: Optional[ObjectId]) -> Optional[str]:
    if o is None:
        return None

    return str(o)


def obj_id(o: Optional[str]) -> Optional[ObjectId]:
    if o is None:
        return None

    return ObjectId(o)


def should_include_ip(actor_type: int, actor_perms: int):
    return actor_type != NOT_AUTHED_USER and actor_perms & PERMISSION_VIEW_IP_ADDR == PERMISSION_VIEW_IP_ADDR


def cinfsum_cmp(c1: Optional[CInfractionSummary], c2: Optional[CInfractionSummary]) -> CInfractionSummary:
    if c1.expiration is None:
        return c1

    if c2.expiration is None:
        return c2

    if c1.expiration > c2.expiration:
        return c1
    else:
        return c2


def cinfsum_cmp_sef(c1: Optional[CInfractionSummary], c2: Optional[CInfractionSummary]) -> bool:
    if c1 is None and c2 is not None:
        return True
    
    if c2 is None:
        return False

    if c1.expiration is None:
        return False

    if c2.expiration is None:
        return True

    if c1.expiration > c2.expiration:
        return False
    else:
        return True


async def cinfsum_inf(db_ref: AsyncIOMotorDatabase, inf: DInfraction) -> CInfractionSummary:

    c = CInfractionSummary(reason=inf.reason, admin_name=await find_admin_name(db_ref, inf.admin))

    if inf.flags & INFRACTION_PERMANENT == INFRACTION_PERMANENT:
        pass
    elif inf.flags & INFRACTION_DEC_ONLINE_ONLY == INFRACTION_DEC_ONLINE_ONLY:
        c.expiration = datetime.now(tz=UTC).timestamp() + inf.time_left
    elif inf.flags & INFRACTION_SESSION == INFRACTION_SESSION:
        c.expiration = 0
    else:
        c.expiration = inf.expires

    return c


def user_str(dinf: DInfraction) -> str:
    if dinf.user is not None:
        return f'{dinf.user.gs_service} {dinf.user.gs_id}'
    elif dinf.ip is not None:
        return dinf.ip
    else:
        raise HTTPException(detail='DB bad infraction format', status_code=500)


async def construct_ci_resp(db_ref, mongo_query: dict) -> CheckInfractionsReply:
    ci_resp = CheckInfractionsReply()

    async for infraction in DInfraction.from_query(db_ref, mongo_query):
        for fn, fi in str2pflag.items():
            if infraction.flags & fi == fi:
                a = getattr(ci_resp, fn)
                x = await cinfsum_inf(db_ref, infraction)

                if a is None:
                    setattr(ci_resp, fn, x)
                else:
                    setattr(ci_resp, fn, cinfsum_cmp(a, x))

    validate(ci_resp)

    return ci_resp


def cim(c1: CheckInfractionsReply, c2: CheckInfractionsReply) -> CheckInfractionsReply:
    return CheckInfractionsReply(
        voice_block=cinfsum_cmp(c1.voice_block, c2.voice_block),
        chat_block=cinfsum_cmp(c1.chat_block, c2.chat_block),
        ban=cinfsum_cmp(c1.ban, c2.ban),
        admin_chat_block=cinfsum_cmp(c1.admin_chat_block, c2.admin_chat_block),
        call_admin_block=cinfsum_cmp(c1.call_admin_block, c2.call_admin_block),
    )
