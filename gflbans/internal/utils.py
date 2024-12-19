import os
import re
import unicodedata
from hashlib import sha512

import orjson
from pydantic import BaseModel, validate_model
from redis.exceptions import RedisError
from starlette.requests import Request


def slash_fix(url):
    if not url.endswith('/'):
        url += '/'
    return url


def or_of_dict_values(d: dict):
    x = 0
    for v in d.values():
        x = x | v
    return x


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


# Returns the key, its hash, and a salt
def generate_api_key():
    key = os.urandom(64).hex()
    salt = os.urandom(32).hex()
    key_hash = str(sha512((key + salt).encode('utf-8')).hexdigest()).upper()
    return key, salt, key_hash


# From Django
def slugify(value, allow_unicode=True):
    """
    Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
    dashes to single dashes. Remove characters that aren't alphanumerics,
    underscores, or hyphens. Convert to lowercase. Also strip leading and
    trailing whitespace, dashes, and underscores.
    """
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize('NFKC', value)
    else:
        value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s.-]', '', value.lower())
    return re.sub(r'[-\s]+', '-', value).strip('.-_')


def get_real_ip(request: Request):
    if 'CF-Connecting-IP' in request.headers:
        return request.headers['CF-Connecting-IP']
    elif 'X-Forwarded-For' in request.headers:
        # Grab the first IP
        x = request.headers['X-Forwarded-For'].strip().split(',')
        return x[0]
    else:
        return request.client.host


def validate(model: BaseModel):
    *_, ve = validate_model(model.__class__, model.__dict__)

    if ve:
        raise ve


class ORJSONSerializer:
    def __init__(self, encoding='utf-8'):
        self.encoding = encoding

    def serialize(self, content):
        try:
            return orjson.dumps(content)
        except Exception as e:
            raise RedisError('Content cannot be encoded') from e

    def deserialize(self, content):
        try:
            return orjson.loads(content)
        except Exception as e:
            raise RedisError('Content cannot be decoded') from e
