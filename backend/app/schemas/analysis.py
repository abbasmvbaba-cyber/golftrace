from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class AnalysisCreate(BaseModel):
    annotation_set_id: str
    engine: str = "classical"
    engine_config: Optional[dict] = None
    idempotency_key: str

class AnalysisResponse(BaseModel):
    id: str
    video_id: str
    annotation_set_snapshot_id: str
    owner_id: str
    engine: str
    engine_config: Optional[dict] = None
    code_version: Optional[str] = None
    status: str
    job_id: Optional[str] = None
    track_version_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
