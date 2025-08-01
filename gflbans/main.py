# Use a virtualenv and execute this script with `python3 -m gflbans.main` to start gflbans

import sys
from datetime import datetime
from multiprocessing import Process
from time import sleep

import uvicorn
from pytz import UTC

from gflbans.internal.config import WEB_PORT, WEB_UNIX, WEB_USE_UNIX, WORKERS
from gflbans.internal.constants import GB_VERSION
from gflbans.internal.log import logger


def start_gflbans():
    logger.info('Starting the API server (uvicorn)')
    if WEB_USE_UNIX:
        logger.debug('Will bind to a UNIX socket')
        uvicorn.run(
            'gflbans.asgi:new_app',
            uds=WEB_UNIX,
            host='127.0.0.1',
            port=WEB_PORT,
            workers=WORKERS,
            factory=True,
            forwarded_allow_ips='*',
        )
    else:
        logger.debug('Will bind to a TCP socket')
        uvicorn.run(
            'gflbans.asgi:new_app',
            host='127.0.0.1',
            port=WEB_PORT,
            workers=WORKERS,
            factory=True,
            forwarded_allow_ips='*',
        )


if __name__ == '__main__':
    logger.info(f'GFLBans {GB_VERSION} by Aurora')

    api = Process(target=start_gflbans)
    api.start()

    proc_t = {'api': []}

    while True:
        sleep(5)

        if not api.is_alive():
            num_last30 = 0

            for t in proc_t['api']:
                if t > datetime.now(tz=UTC).timestamp() - 30:
                    num_last30 += 1

            if num_last30 >= 3:
                logger.fatal('API has died more than 3 times in the past 30 seconds! Bailing out!')
                sys.exit(1)

            logger.error(f'API died! Restarting... ({num_last30} / 3)')

            api = Process(target=start_gflbans)
            api.start()

            proc_t['api'].append(datetime.now(tz=UTC).timestamp())
