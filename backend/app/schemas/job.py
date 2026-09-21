from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class JobResponse(BaseModel):
    id: str
    type: str
    owner_id: Optional[str] = None
    project_id: Optional[str] = None
    video_id: Optional[str] = None
    status: str
    attempt: int
    max_attempts: int
    progress: Optional[dict] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True
