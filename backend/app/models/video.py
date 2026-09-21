import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func, ForeignKey, Integer, BigInteger, Boolean, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base

class Video(Base):
    __tablename__ = "videos"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(512))
    storage_key: Mapped[str] = mapped_column(String(1024))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    duration_us: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)  # canonical width
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    encoded_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    encoded_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rotation: Mapped[int] = mapped_column(Integer, default=0)
    fps_avg: Mapped[float | None] = mapped_column(nullable=True)
    fps_max: Mapped[float | None] = mapped_column(nullable=True)
    is_vfr: Mapped[bool] = mapped_column(Boolean, default=False)
    codec: Mapped[str | None] = mapped_column(String(64), nullable=True)
    has_audio: Mapped[bool] = mapped_column(Boolean, default=False)
    probe_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    preparation_status: Mapped[str] = mapped_column(String(30), default="pending")  # pending/probing/manifesting/previewing/ready/failed
    preparation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    frame_manifest_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    preview_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class FrameManifest(Base):
    __tablename__ = "frame_manifests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    video_id: Mapped[str] = mapped_column(String(36), ForeignKey("videos.id"), index=True)
    storage_key: Mapped[str] = mapped_column(String(1024))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    frame_count: Mapped[int] = mapped_column(Integer)
    duration_us: Mapped[int] = mapped_column(BigInteger)
    vfr: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
