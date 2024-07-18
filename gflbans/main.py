# Use a virtualenv and execute this script with `python3 -m gflbans.main` to start gflbans

from multiprocessing import Queue, Process
from functools import partial
from time import sleep
from datetime import date, datetime

import uvicorn
import sys
from pytz import UTC

from gflbans.internal.config import WEB_USE_UNIX, WEB_UNIX, WEB_PORT, WORKERS, DISCORD_BOT_TOKEN
from gflbans.internal.log import logger
from gflbans.internal.constants import GB_VERSION
from gflbans.asgi import new_app

def start_gflbans():
    logger.info('Starting the API server (uvicorn)')
    if WEB_USE_UNIX:
        logger.debug('Will bind to a UNIX socket')
        uvicorn.run('gflbans.main:new_app', uds=WEB_UNIX, host='127.0.0.1', port=WEB_PORT, workers=WORKERS, factory=True, forwarded_allow_ips='*')
    else:
        logger.debug('Will bind to a TCP socket')
        uvicorn.run('gflbans.main:new_app', host='127.0.0.1', port=WEB_PORT, workers=WORKERS, factory=True, forwarded_allow_ips='*')


if __name__ == '__main__':
    logger.info(f'GFLBans {GB_VERSION} by Aurora')

    api = Process(target=start_gflbans)
    api.start()
    
    
    proc_t = {
        'api': []
    }

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
