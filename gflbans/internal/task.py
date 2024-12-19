import asyncio
from asyncio import CancelledError
from datetime import datetime
from typing import Dict

from dateutil.tz import UTC

from gflbans.internal.config import MONGO_DB
from gflbans.internal.database.task import DTask
from gflbans.internal.log import logger
from gflbans.internal.tasks.infraction import GetUserData, GetVPNData
from gflbans.internal.tasks.task import TaskBase

TASK_HANDLERS: Dict[str, TaskBase] = {'get_vpn_data': GetVPNData, 'get_user_data': GetUserData}


async def exec_loop(app_ref):
    task = await DTask.pop_next_task(app_ref.state.db[MONGO_DB])
    if task is None:
        await asyncio.sleep(1)
        return

    if task.ev_handler not in TASK_HANDLERS:
        logger.error(f'Tried to execute task {task.ev_handler}, but there is no handler for that task')
        return

    task_handler = TASK_HANDLERS[task.ev_handler]

    # Attempt to run the task
    try:
        await task_handler.handler(app_ref, task.task_data)
    except Exception as e:
        logger.error('Task failed', exc_info=e)

        if task_handler.allow_retry and task.failure_count <= len(task_handler.backoffs) - 1:
            task.run_at = datetime.now(tz=UTC).timestamp() + task_handler.backoffs[task.failure_count]
            task.failure_count += 1

            await task.commit(app_ref.state.db[MONGO_DB])

        if isinstance(e, CancelledError):
            raise

    await asyncio.sleep(0.1)


async def task_loop(app_ref):
    while True:
        try:
            await exec_loop(app_ref)
        except Exception as e:
            logger.error('Internal task manager error', exc_info=e)

            if isinstance(e, CancelledError):
                raise
