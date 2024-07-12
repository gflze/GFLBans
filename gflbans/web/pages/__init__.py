from datetime import datetime

from pytz import UTC
from starlette.requests import Request

from gflbans.internal.config import BRANDING
from gflbans.internal.flags import name2perms
from gflbans.web.data import THEME, GB_VERSION
from gflbans.web.login import current_user


async def sctx(request: Request) -> dict:
    theme = THEME['light'] if 'dark_mode' not in request.session or not request.session['dark_mode'] else THEME['dark']

    user = await current_user(request)

    return {'request': request, 'theme': theme, 'user': user, 'p_nodes': name2perms, 'GB_VERSION': GB_VERSION,
            'GB_BEGIN_RENDER': datetime.now(tz=UTC).timestamp(), 'BRANDING': BRANDING}
