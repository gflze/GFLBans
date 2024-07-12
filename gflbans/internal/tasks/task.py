from typing import Callable, List

from pydantic import BaseModel, conint


class TaskBase(BaseModel):
    handler: Callable
    allow_retry: bool = True
    backoffs: List[conint(ge=0)] = []
