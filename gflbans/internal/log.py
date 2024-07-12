import logging

from uvicorn.logging import ColourizedFormatter

logger = logging.getLogger('gflbans')
logger.setLevel(logging.DEBUG)

sh = logging.StreamHandler()
cf = ColourizedFormatter('%(levelprefix)s %(message)s')
sh.setFormatter(cf)
logger.addHandler(sh)
