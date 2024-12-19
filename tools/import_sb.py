#! /usr/bin/env python3

import asyncio
import math
from datetime import datetime

import aiohttp
import aiomysql
from pytz import UTC


def default(v, d):
    if v == '':
        return d
    else:
        return v


gflbans_instance = default(input('GFLBans Instance [https://bans.gflclan.com/]: '), 'https://bans.gflclan.com/')
gflbans_api_key_id = default(input('GFLBans API Key ID [no default]: '), 'no default')
gflbans_api_key_secret = default(input('GFLBans API Key Secret [no default]: '), 'no default')

mysql_host = default(input('SourceBans MySQL Host [127.0.0.1]: '), '127.0.0.1')
mysql_user = default(input('SourceBans MySQL User [root]: '), 'root')
mysql_pass = default(input('SourceBans MySQL Pass [password]: '), 'password')
mysql_port = int(default(input('SourceBans MySQL Port [3306]: '), '3306'))
mysql_db = default(input('SourceBans MySQL Database [site_sourcebans]: '), 'site_sourcebans')

checkpoint_bans = int(default(input('Bans import checkpoint [0]'), '0'))
checkpoint_comms = int(default(input('Comms import checkpoint [0]'), '0'))

session = aiohttp.ClientSession()


def id_to_64(steamid):
    if steamid == 'STEAM_ID_SERVER':
        return None

    steamid = steamid[6:].split(':')  # remove STEAM_ and split into 3 components

    if len(steamid) != 3:
        return None  # invalid

    y = int(steamid[1])
    z = int(steamid[2])

    return (z * 2) + y + 0x0110000100000000


def slash_fix(url: str) -> str:
    if not url.endswith('/'):
        return url + '/'

    return url


# don't want to overwhelm the server by running 200k+ requests at the same time
async def batched(coros):
    processed = 0
    for i in range(int(math.ceil(len(coros) / 10))):
        d = []
        for i2 in range(10):
            idx = (i * 10) + i2
            if len(coros) > idx:
                d.append(coros[idx])
                processed += 1

        await asyncio.gather(*d)

    return processed


async def process_ban(adminid64, ban):
    try:
        # skip expired and removed bans
        if (ban[6] > 0 and ban[5] < datetime.now(tz=UTC).timestamp()) or (ban[13] and ban[13] != ''):
            print(f'skip ban {ban[0]} as it is expired or removed.')
            return

        api_req = {
            'created': ban[4],
            'player': {},
            'punishments': ['ban'],
            'import_mode': True,
            'scope': 'global',  # all sourcebans were global
        }

        if adminid64:
            api_req['admin'] = {'gs_admin': {'gs_service': 'steam', 'gs_id': adminid64}}

        if ban[2] and ban[2] != '' and id_to_64(ban[2]):
            api_req['player']['gs_service'] = 'steam'
            api_req['player']['gs_id'] = id_to_64(ban[2])

        if ban[1] and ban[1] != '':
            api_req['player']['ip'] = ban[1]

        if 'ip' not in api_req['player'] and ('gs_id' not in api_req['player'] or not api_req['player']['gs_id']):
            print(f'could not find a valid player id, skipping {ban[0]}')
            return

        if ban[7] and ban[7] != '':
            api_req['reason'] = ban[7][:279]
        else:
            api_req['reason'] = 'No Reason Specified'

        if ban[6] <= 0:
            pass  # permanent bans are when duration is omitted
        else:
            api_req['duration'] = ban[5] - ban[4]  # sets the duration to the time remaining

        async with session.post(
            f'{slash_fix(gflbans_instance)}api/infractions/',
            headers={
                'Authorization': f'API {gflbans_api_key_id} {gflbans_api_key_secret}',
                'Content-Type': 'application/json',
            },
            json=api_req,
        ) as resp:
            if resp.status >= 400:
                print(f'failed to create infraction (HTTP {resp.status}): {await resp.text()}, api request:')
                print(api_req)
                return

            j = await resp.json()

            print(f'created infraction {j["id"]}')

        print(f'processed ban {ban[0]}')
    except Exception as e:
        print(f'could not process ban {ban[0]}: {e}')


async def process_comm(adminid64, comm):
    try:
        # skip expired and removed bans
        if (comm[5] > 0 and comm[4] < datetime.now(tz=UTC).timestamp()) or (comm[11] and comm[11] != ''):
            print(f'skip comm {comm[0]} as it is expired or removed.')
            return

        api_req = {
            'created': comm[3],
            'player': {'gs_service': 'steam', 'gs_id': id_to_64(comm[1])},
            'import_mode': True,
            'scope': 'global',  # all sourcebans were global
        }

        if not api_req['player']['gs_id']:
            print(f'failed parsing steamid for comm {comm[0]}')
            return

        if adminid64:
            api_req['admin'] = {'gs_admin': {'gs_service': 'steam', 'gs_id': adminid64}}

        if comm[6] and comm[6] != '' and len(comm[6]) <= 120:
            api_req['reason'] = comm[6][:279]
        else:
            api_req['reason'] = 'No Reason Specified'

        if comm[5] == 0:
            pass  # permanent bans are when duration is omitted
        elif comm[5] < 0:
            api_req['session'] = True
        else:
            api_req['duration'] = comm[4] - comm[3]  # Sets the duration to the time remaining

        if comm[13] == 1:
            api_req['punishments'] = ['voice_block']
        else:
            api_req['punishments'] = ['chat_block']

        async with session.post(
            f'{slash_fix(gflbans_instance)}api/infractions/',
            headers={
                'Authorization': f'API {gflbans_api_key_id} {gflbans_api_key_secret}',
                'Content-Type': 'application/json',
            },
            json=api_req,
        ) as resp:
            if resp.status >= 400:
                print(f'failed to create infraction (HTTP {resp.status}): {await resp.text()}')
                return

            j = await resp.json()

            print(f'created infraction {j["id"]}')

        print(f'processed comm {comm[0]}')
    except Exception as e:
        print(f'could not process ban {comm[0]}: {e}')


async def moin():
    conn = await aiomysql.connect(
        host=mysql_host,
        port=mysql_port,
        user=mysql_user,
        password=mysql_pass,
        db=mysql_db,
        loop=asyncio.get_running_loop(),
    )

    print('fetch admins')

    # load admins
    async with conn.cursor() as admin_cur:
        await admin_cur.execute('SELECT * FROM sb_admins;')

        admins = await admin_cur.fetchall()

        adminid_to_steamid64 = {}

        for admin in admins:
            admin_steamid = admin[2]  # authid

            adminid_to_steamid64[admin[0]] = id_to_64(admin_steamid)

    print(f'fetched {len(adminid_to_steamid64)} admins')

    async with conn.cursor() as bans_cur:
        print(f'converting bans after {checkpoint_bans}')

        await bans_cur.execute('SELECT *  FROM sb_bans;')
        bans = await bans_cur.fetchall()

        b = []

        print(f'{len(bans)} bans to convert')

        for ban in bans:
            if ban[0] <= checkpoint_bans:
                print(f'skipping {ban[0]} to get to the checkpoint')

            if ban[8] in adminid_to_steamid64:
                adm = adminid_to_steamid64[ban[8]]
            else:
                adm = None
            b.append(process_ban(adm, ban))

        print(f'processed {await batched(b)} bans')

    print('converting comms')

    async with conn.cursor() as comms_cur:
        await comms_cur.execute('SELECT * FROM sb_comms;')
        comms = await comms_cur.fetchall()

    c = []

    print(f'{len(comms)} comms to convert')

    for comm in comms:
        if comm[0] <= checkpoint_comms:
            print(f'skipping {comm[0]} to get to the checkpoint')
            continue

        if comm[7] in adminid_to_steamid64:
            adm = adminid_to_steamid64[comm[7]]
        else:
            adm = None

        c.append(process_comm(adm, comm))

    print(f'processed {await batched(c)} comms')

    print('all done!')

    print(f'ban checkpoint: {ban[0]}')
    print(f'comms checkpoint: {comm[0]}')


if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(moin())
