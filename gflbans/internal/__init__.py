import os

VERSION = '0.4-ALPHA'

# This is really only for logging purposes
shard: str = str(os.urandom(32).hex())

