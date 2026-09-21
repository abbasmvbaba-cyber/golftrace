from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ProjectCreate(BaseModel):
    title: Optional[str] = "Untitled Project"
    description: Optional[str] = None
    idempotency_key: str

class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    version: int

class ProjectResponse(BaseModel):
    id: str
    owner_id: str
    title: str
    description: Optional[str] = None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
