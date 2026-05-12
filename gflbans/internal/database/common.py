from datetime import datetime
from typing import Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict


class DFile(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    gridfs_file: str
    file_name: str = 'avatar.webp'
    uploaded_by: Optional[ObjectId] = None
    private: bool = False
    created: Optional[datetime] = None


class DUser(BaseModel):
    gs_service: str
    gs_id: str
    gs_avatar: Optional[DFile] = None
    gs_name: Optional[str] = None
