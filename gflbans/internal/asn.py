from contextlib import suppress

from aredis import RedisError
from aredis.cache import IdentityGenerator
from netaddr import IPAddress

from gflbans.internal.config import MONGO_DB
from gflbans.internal.database.vpn import DVPN
from gflbans.internal.log import logger


class IPInfoIdentityGenerator(IdentityGenerator):
    def generate(self, key, typ):
        return 'IPInfo::%s:%s' % (typ, key)


VPN_YES = 0
VPN_NO = 1
VPN_CLOUD = 2


async def check_vpn(app, ip_addr: str) -> int:

    # Wtf is ip2asn.gflclan.com?
    # Whatever it is, we don't have it, and it breaks infraction loading
    # And no VPN integration is on gameserver yet anyways, so we're losing nothing by doing this
    return VPN_NO

    a = None

    with suppress(RedisError):
        a = await app.state.ip_info_cache.get(ip_addr, 'asninfo')

    if a is None:
        async with app.state.aio_session.get(f'https://ip2asn.gflclan.com/v1/as/ip/{ip_addr}') as resp:
            try:
                resp.raise_for_status()
            except Exception:
                logger.error('Call to iptoasn API failed!', exc_info=True)
                raise

            a = await resp.json()
            with suppress(RedisError):
                await app.state.ip_info_cache.set(ip_addr, a, 'asninfo', expire_time=60*10)

    if 'as_number' in a:
        asn = a['as_number']

        b = await DVPN.find_one_from_query(app.state.db[MONGO_DB], {'payload': str(asn), 'payload_type': True})

        if b is not None:
            if b.is_cloud:
                logger.info(f'{ip_addr} is a cloud gaming provider ip address per asn rule {b.payload} ({b.id})')
                return VPN_CLOUD
            else:
                logger.info(f'{ip_addr} is a VPN ip address per asn rule {b.payload} ({b.id})')
                return VPN_YES

    ipd = await DVPN.find_cidr_rule(app.state.db[MONGO_DB], IPAddress(ip_addr))

    if ipd is not None:
        if ipd.is_cloud:
            logger.info(f'{ip_addr} is a cloud gaming provider ip address per CIDR rule {ipd.payload} ({ipd.id})')
            return VPN_CLOUD
        else:
            logger.info(f'{ip_addr} is a VPN ip address per CIDR rule {ipd.payload} ({ipd.id})')
            return VPN_YES

    return VPN_NO

