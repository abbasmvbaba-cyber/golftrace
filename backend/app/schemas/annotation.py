from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class AnnotationInput(BaseModel):
    frame_index: int
    x_norm: Optional[float] = None
    y_norm: Optional[float] = None
    visibility: str = "visible"  # visible/not_visible/out_of_frame

class AnnotationSetCreate(BaseModel):
    analysis_interval: Optional[dict] = None  # {start_frame, end_frame}
    annotations: List[AnnotationInput]
    idempotency_key: str
    parent_id: Optional[str] = None

class AnnotationResponse(BaseModel):
    id: str
    annotation_set_id: str
    frame_index: int
    x_norm: Optional[float] = None
    y_norm: Optional[float] = None
    visibility: str
    provenance: str
    created_at: datetime

    class Config:
        from_attributes = True

class AnnotationSetResponse(BaseModel):
    id: str
    video_id: str
    owner_id: str
    version: int
    is_snapshot: bool
    parent_id: Optional[str] = None
    created_at: datetime
    metadata: Optional[dict] = None
    annotations: List[AnnotationResponse]

    class Config:
        from_attributes = True
