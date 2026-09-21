from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class RenderCreate(BaseModel):
    style: dict
    export: Optional[dict] = None
    idempotency_key: str

class RenderResponse(BaseModel):
    id: str
    track_version_id: str
    owner_id: str
    video_id: str
    style_snapshot: Optional[dict] = None
    status: str
    job_id: Optional[str] = None
    output_storage_key: Optional[str] = None
    output_metadata: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True

class RenderDownloadResponse(BaseModel):
    url: str
    expires_at: datetime
