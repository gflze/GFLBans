from typing import List, Optional

from bson import ObjectId
from pydantic import BaseModel, conint, constr

from gflbans.internal.database.base import DBase
from gflbans.internal.flags import valid_types_regex


class DTieringPolicyTier(BaseModel):
    punishments: List[constr(regex=valid_types_regex)]
    duration: conint(ge=0)
    dec_online: bool = False


class DTieringPolicy(DBase):
    name: str
    server: Optional[ObjectId]
    tiers: List[DTieringPolicyTier]
    include_other_servers: bool = True
    tier_ttl: int
    reason: constr(min_length=1, max_length=280)
