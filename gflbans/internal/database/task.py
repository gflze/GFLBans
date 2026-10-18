from datetime import datetime
from typing import ClassVar

from dateutil.tz import UTC
from pydantic import PositiveFloat, conint
from pymongo.asynchronous.database import AsyncDatabase

from gflbans.internal.database.base import DBase
from gflbans.internal.log import logger


class DTask(DBase):
    __collection__: ClassVar[str] = 'tasks'

    run_at: PositiveFloat
    failure_count: conint(ge=0) = 0
    task_data: dict
    ev_handler: str

    @classmethod
    async def pop_next_task(cls, db_ref: AsyncDatabase):
        task = await db_ref[cls.__collection__].find_one_and_delete(
            {'run_at': {'$lte': datetime.now(tz=UTC).timestamp()}}
        )

        if task is None:
            return None  # no task

        logger.debug(f'Popped task {str(task["_id"])} from the task queue')

        # kill the task id since it was deleted
        dtask = cls.load_document(task)
        dtask.id = None

        return dtask
