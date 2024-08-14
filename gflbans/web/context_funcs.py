# Jinja2 has no bitwise operators
from datetime import datetime

from pytz import UTC


def has_flag(flags: int, flag: int) -> bool:
    return flags & flag


def bit_or(*args) -> int:
    r = 0

    for arg in args:
        r |= arg

    return r


# Used to estimate render time
# Technically speaking, there is some render work left to be done on most pages upon the execution of this function
# so this is truly only the best estimate we are currently capable of
def render_time(beg):
    rt = datetime.now(tz=UTC).timestamp() - beg

    # Use either micro or millis depending on the magnitude of the time
    if rt < 0.005:
        unit = 'µ'
        rt = rt * 1000000
    else:
        unit = 'm'
        rt = rt * 1000

    return f'{round(rt)} {unit}s'


def tostring(obj):
    return str(obj)


def caps(s: str):
    return s.upper()
