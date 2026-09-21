from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class UploadCreate(BaseModel):
    filename: str
    size_bytes: int
    content_type: Optional[str] = None
    idempotency_key: str

class UploadResponse(BaseModel):
    upload_id: str
    upload_url: Optional[str] = None
    storage_key: str
    expires_at: datetime

class UploadCompleteRequest(BaseModel):
    size_bytes: Optional[int] = None

class UploadCompleteResponse(BaseModel):
    video_id: str
    job_id: str
