import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func, ForeignKey, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    type: Mapped[str] = mapped_column(String(30))  # video_preparation, tracking, rendering, cleanup, maintenance
    owner_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("projects.id"), nullable=True)
    video_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("videos.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued/claimed/running/succeeded/failed/cancelled
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    fencing_token: Mapped[str] = mapped_column(String(36), default=lambda: str(uuid.uuid4()))
    progress: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
