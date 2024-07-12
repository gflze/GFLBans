from datetime import datetime
from typing import Optional

from bson import ObjectId
from pydantic.main import BaseModel


class DFile(BaseModel):
    gridfs_file: str
    file_name: str = 'avatar.webp'
    uploaded_by: Optional[ObjectId]
    private: bool = False
    created: Optional[datetime]

    class Config:
        arbitrary_types_allowed = True


class DUser(BaseModel):
    gs_service: str
    gs_id: str
    gs_avatar: Optional[DFile]
    gs_name: Optional[str]
