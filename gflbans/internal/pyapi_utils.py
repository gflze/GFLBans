from aiohttp import ClientResponseError
from bson.objectid import ObjectId
from starlette.exceptions import HTTPException

from gflbans.internal.config import MONGO_DB
from gflbans.internal.constants import AUTHED_USER
from gflbans.internal.database.admin import Admin
from gflbans.internal.database.dadmin import DAdmin
from gflbans.internal.errors import NoSuchAdminError
from gflbans.internal.integrations.ips import ips_get_member_id_from_gsid
from gflbans.internal.log import logger
from gflbans.internal.models.api import Initiator


async def load_admin_from_initiator(app, admin: Initiator):
    if admin.ips_id:
        a = Admin(admin.ips_id)
        await a.fetch_details(app)
        return a
    elif admin.mongo_id:
        a = await DAdmin.from_id(app.state.db[MONGO_DB], ObjectId(admin.mongo_id))

        if a is None:
            raise NoSuchAdminError('Could not find an admin with that id')

        a = Admin(a.ips_user)
        await a.fetch_details(app)
        return a
    else:
        a = Admin(ips_get_member_id_from_gsid(admin.gs_admin.gs_id))
        await a.fetch_details(app)
        return a


async def load_admin(request, admin_initiator):
    try:
        return await load_admin_from_initiator(request.app, admin_initiator)
    except NoSuchAdminError:
        raise HTTPException(detail='Could not find an admin with which to associate this' 'infraction', status_code=403)
    except ClientResponseError as e:
        logger.error('Error whilst communicating with the forums', exc_info=e)
        raise HTTPException(detail='Internal Server Error', status_code=500)


# Get admin that the authenticator is acting for (or at least claims to be acting for)
async def get_acting(request, admin_initiator, auth_type, auth_id) -> Admin:
    if auth_type == AUTHED_USER:
        acting_admin = await load_admin(request, Initiator(mongo_id=str(auth_id)))
    elif admin_initiator is None:
        acting_admin = Admin(0)
        await acting_admin.fetch_details(request.app)
    else:
        acting_admin = await load_admin(request, admin_initiator)

    return acting_admin
