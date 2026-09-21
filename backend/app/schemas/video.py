from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class VideoResponse(BaseModel):
    id: str
    project_id: str
    owner_id: str
    original_filename: str
    size_bytes: int
    duration_us: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    encoded_width: Optional[int] = None
    encoded_height: Optional[int] = None
    rotation: int
    fps_avg: Optional[float] = None
    fps_max: Optional[float] = None
    is_vfr: bool
    codec: Optional[str] = None
    has_audio: bool
    preparation_status: str
    preparation_error: Optional[str] = None
    frame_manifest_key: Optional[str] = None
    preview_key: Optional[str] = None
    thumbnail_key: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class PlaybackResponse(BaseModel):
    url: str
    expires_at: datetime

class FrameManifestResponse(BaseModel):
    manifest: dict
