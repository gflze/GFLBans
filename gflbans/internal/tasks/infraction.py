from gflbans.internal.infraction_utils import get_user_data, get_vpn_data
from gflbans.internal.tasks.task import TaskBase


async def ev_get_vpn_data(app, data):
    await get_vpn_data(app, data['i_id'], False)


async def ev_get_user_data(app, data):
    await get_user_data(app, data['i_id'], False)


GetVPNData = TaskBase(handler=ev_get_vpn_data, backoffs=[30, 60, 180, 360, 720, 3600, 3600 * 24, 3600 * 7])
GetUserData = TaskBase(handler=ev_get_user_data, backoffs=[30, 60, 180, 360, 720, 3600, 3600 * 24, 3600 * 7])
