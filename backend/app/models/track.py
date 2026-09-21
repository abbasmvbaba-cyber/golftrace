import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func, ForeignKey, Integer, BigInteger, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base

class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    video_id: Mapped[str] = mapped_column(String(36), ForeignKey("videos.id"), index=True)
    annotation_set_snapshot_id: Mapped[str] = mapped_column(String(36), ForeignKey("annotation_sets.id"))
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    engine: Mapped[str] = mapped_column(String(20), default="classical")
    engine_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    code_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=True)
    track_version_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("track_versions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class TrackVersion(Base):
    __tablename__ = "track_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    video_id: Mapped[str] = mapped_column(String(36), ForeignKey("videos.id"), index=True)
    analysis_run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("analysis_runs.id"), nullable=True)
    parent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("track_versions.id"), nullable=True)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    storage_key: Mapped[str] = mapped_column(String(1024))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    frame_count: Mapped[int] = mapped_column(Integer, default=0)
    provenance_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class RenderJob(Base):
    __tablename__ = "render_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    track_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("track_versions.id"), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    video_id: Mapped[str] = mapped_column(String(36), ForeignKey("videos.id"), index=True)
    style_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=True)
    output_storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    output_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
