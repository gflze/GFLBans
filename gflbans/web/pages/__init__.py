from datetime import datetime

from pytz import UTC
from starlette.requests import Request

from gflbans.internal.config import BRANDING, DISABLE_GUIDELINES
from gflbans.internal.constants import GB_VERSION
from gflbans.internal.flags import name2perms
from gflbans.web.login import current_user


async def sctx(request: Request) -> dict:
    opposite_theme = True if 'opposite_theme' in request.session and request.session['opposite_theme'] else False
    user = await current_user(request)

    return {
        'request': request,
        'opposite_theme': opposite_theme,
        'user': user,
        'p_nodes': name2perms,
        'GB_VERSION': GB_VERSION,
        'GB_BEGIN_RENDER': datetime.now(tz=UTC).timestamp(),
        'BRANDING': BRANDING,
        'DISABLE_GUIDELINES': DISABLE_GUIDELINES,
    }
