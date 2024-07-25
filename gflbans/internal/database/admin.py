from datetime import datetime
from typing import Optional

from bson import ObjectId
from dateutil.tz import UTC

from gflbans.internal.config import ROOT_USER, MONGO_DB
from gflbans.internal.database.common import DFile
from gflbans.internal.database.dadmin import DAdmin
from gflbans.internal.database.group import DGroup
from gflbans.internal.flags import ALL_PERMISSIONS, PERMISSION_VPN_CHECK_SKIP
from gflbans.internal.integrations.ips import get_member_by_id_nc, ips_process_avatar


class Admin:
    def __init__(self, admin=0):
        self.__ips_id = admin

        self.__loaded = False
        self.__dadmin: Optional[DAdmin] = None
        self.__vpn_immunity = False

        self.__calc_privs = 0

        if admin == 0:
            self.__loaded = True

    async def fetch_details(self, app):
        if self.__ips_id == 0:
            return

        # Pull it from the cache
        self.__dadmin = await DAdmin.from_ips_user(app.state.db[MONGO_DB], self.__ips_id)

        if self.__dadmin is None:
            self.__dadmin = DAdmin(ips_user=self.__ips_id)

        # Update if the next update time is less than the current time
        if self.__dadmin.last_updated == 0 or self.__dadmin.last_updated + 600 <= datetime.now(tz=UTC).\
                timestamp():
            adm_data = await get_member_by_id_nc(app, self.__dadmin.ips_user)
            self.__dadmin.last_updated = datetime.now(tz=UTC).timestamp()
            self.__dadmin.name = adm_data['name']
            try:
                av = DFile(**await ips_process_avatar(app, adm_data['photoUrl']))
            except:
                av = None

            if av is not None:
                self.__dadmin.avatar = av

            i_grps = []

            for grp in adm_data['groups']:
                if grp not in i_grps:
                    i_grps.append(grp)

            self.__dadmin.groups = i_grps

            await self.__dadmin.commit(app.state.db[MONGO_DB])

        if self.__dadmin.vpn_whitelist:
            self.__vpn_immunity = True

        if self.__dadmin.ips_user != ROOT_USER:
            for grp in self.__dadmin.groups:
                g = await DGroup.find_one_from_query(app.state.db[MONGO_DB], {'ips_group': grp})

                if g is not None:
                    self.__calc_privs |= g.privileges

        self.__loaded = True

    @property
    def permissions(self):
        if not self.__loaded:
            raise ValueError('Attempted to access Admin object before initialized.')

        privs = ALL_PERMISSIONS if self.__ips_id == 0 or self.__ips_id == ROOT_USER else self.__calc_privs

        if self.__vpn_immunity:
            privs |= PERMISSION_VPN_CHECK_SKIP

        return privs

    @property
    def avatar(self) -> Optional[DFile]:
        if not self.__loaded:
            raise ValueError('Attempted to access Admin object before initialized.')

        if self.__ips_id == 0: return None

        return self.__dadmin.avatar

    @property
    def name(self) -> str:
        if not self.__loaded:
            raise ValueError('Attempted to access Admin object before initialized.')

        if self.__ips_id == 0: return 'SYSTEM'

        return self.__dadmin.name

    @property
    def mongo_admin_id(self) -> Optional[ObjectId]:
        if not self.__loaded:
            raise ValueError('Attempted to access Admin object before initialized.')

        if self.__ips_id == 0:
            return None

        return self.__dadmin.id

    @property
    def ips_id(self):
        if not self.__loaded:
            raise ValueError('Attempted to access Admin object before initialized.')

        return self.__ips_id

    @property
    def db(self):
        if self.__dadmin:
            return self.__dadmin
        else:
            return None