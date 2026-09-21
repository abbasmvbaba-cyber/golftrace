from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class TrackVersionResponse(BaseModel):
    id: str
    video_id: str
    analysis_run_id: Optional[str] = None
    parent_id: Optional[str] = None
    owner_id: str
    storage_key: str
    schema_version: int
    frame_count: int
    provenance_summary: Optional[dict] = None
    is_manual: bool
    created_at: datetime

    class Config:
        from_attributes = True

class TrackDataResponse(BaseModel):
    track_version: TrackVersionResponse
    points: List[dict]

class TrackRevisionCreate(BaseModel):
    annotations: List[dict]  # same as annotation input
    reason: Optional[str] = None
    idempotency_key: str
