import re
from datetime import datetime

from packaging.version import Version
from pytz import UTC
from starlette.requests import Request

from gflbans.internal.config import BRANDING, DISABLE_GUIDELINES, ROOT_USER
from gflbans.internal.constants import GB_VERSION
from gflbans.internal.flags import name2perms
from gflbans.internal.log import logger
from gflbans.web.login import current_user


async def sctx(request: Request) -> dict:
    opposite_theme = True if 'opposite_theme' in request.session and request.session['opposite_theme'] else False
    user = await current_user(request)

    update_available = False
    if user.ips_id == ROOT_USER:
        async with request.app.state.aio_session.get(
            'https://raw.githubusercontent.com/gflze/GFLBans/refs/heads/main/gflbans/internal/constants.py'
        ) as response:
            try:
                response.raise_for_status()
                text = await response.text()
                upstream_version = Version(re.search(r'GB_VERSION\s*=\s*["\'](.+?)["\']', text).group(1))
                update_available = upstream_version > Version(GB_VERSION)
            except Exception:
                logger.error('Failed to fetch upstream GFLBans version.', exc_info=True)

    return {
        'request': request,
        'opposite_theme': opposite_theme,
        'user': user,
        'p_nodes': name2perms,
        'GB_VERSION': GB_VERSION,
        'GB_BEGIN_RENDER': datetime.now(tz=UTC).timestamp(),
        'BRANDING': BRANDING,
        'DISABLE_GUIDELINES': DISABLE_GUIDELINES,
        'UPDATE_AVAILABLE': update_available,
    }
