import uuid
from datetime import datetime, timedelta
from sqlalchemy import String, DateTime, func, ForeignKey, BigInteger
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base

class UploadSession(Base):
    __tablename__ = "upload_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), index=True)
    video_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("videos.id"), nullable=True)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(String(512))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    storage_key: Mapped[str] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(20), default="created")  # created/uploading/completed/failed/aborted
    upload_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow() + timedelta(hours=1))
