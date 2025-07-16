from contextlib import suppress

from netaddr import IPAddress
from redis.exceptions import RedisError

from gflbans.internal.config import IPHUB_API_KEY, IPHUB_CACHE_TIME, MONGO_DB
from gflbans.internal.database.vpn import DVPN
from gflbans.internal.log import logger

VPN_NO = 0
VPN_YES = 1
VPN_DUBIOUS = 2


async def check_vpn(app, ip_addr: str) -> int:
    iphub_data = None
    iphub_call_exception = None
    with suppress(RedisError):
        iphub_data = await app.state.ip_info_cache.get(ip_addr, 'iphubinfo')

    if iphub_data is None and IPHUB_API_KEY is not None and IPHUB_API_KEY != 'APIKEYHERE':
        headers = {'X-Key': IPHUB_API_KEY}
        async with app.state.aio_session.get(f'https://v2.api.iphub.info/ip/{ip_addr}', headers=headers) as resp:
            try:
                resp.raise_for_status()

                if resp.status == 429:
                    logger.warning('Rate limit exceeded for IPHub API')
                else:
                    iphub_data = await resp.json()
                    with suppress(RedisError):
                        await app.state.ip_info_cache.set(
                            ip_addr,
                            iphub_data,
                            'iphubinfo',
                            expire_time=IPHUB_CACHE_TIME,  # Cache for 1 week
                        )

            except Exception as e:
                logger.error('Call to IPHub API failed.', exc_info=e)
                iphub_call_exception = e
                # Dont return False yet, as we still can check cidr rule for manually defined ASNs

    if iphub_data and iphub_data.get('block', 0) == 1:
        logger.info(f'{ip_addr} is marked as VPN/proxy by IPHub')
        return VPN_YES

    is_dubious = False
    if iphub_data and iphub_data.get('block', 0) == 2:
        logger.info(f'{ip_addr} is marked as a suspicious IP by IPHub')
        is_dubious = True

    # If IPHub says it's not a VPN (block=0), check our DVPN database for if we block that ASN
    if iphub_data and iphub_data.get('asn'):
        asn = iphub_data['asn']
        asn_vpn = await DVPN.find_one_from_query(app.state.db[MONGO_DB], {'payload': str(asn), 'is_asn': True})

        if asn_vpn is not None:
            if not asn_vpn.is_dubious:
                logger.info(f'{ip_addr} is a VPN ip address per ASN rule {asn_vpn.payload} ({asn_vpn.id})')
                return VPN_YES
            else:
                logger.info(f'{ip_addr} is a suspicious ip address per ASN rule {asn_vpn.payload} ({asn_vpn.id})')
                is_dubious = True

    # Check for CIDR rules in our database for if we block that IP block
    cidr_vpn = await DVPN.find_cidr_rule(app.state.db[MONGO_DB], IPAddress(ip_addr))

    if cidr_vpn is not None:
        if not cidr_vpn.is_dubious:
            logger.info(f'{ip_addr} is a VPN ip address per CIDR rule {cidr_vpn.payload} ({cidr_vpn.id})')
            return VPN_YES
        else:
            logger.info(f'{ip_addr} is a suspicious ip address per CIDR rule {cidr_vpn.payload} ({cidr_vpn.id})')
            is_dubious = True

    if iphub_call_exception is not None and not is_dubious:
        raise iphub_call_exception

    return VPN_DUBIOUS if is_dubious else VPN_NO
