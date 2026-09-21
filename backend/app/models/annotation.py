import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func, ForeignKey, Integer, Boolean, JSON, Float
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base

class AnnotationSet(Base):
    __tablename__ = "annotation_sets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    video_id: Mapped[str] = mapped_column(String(36), ForeignKey("videos.id"), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_snapshot: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("annotation_sets.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)  # analysis interval

class Annotation(Base):
    __tablename__ = "annotations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    annotation_set_id: Mapped[str] = mapped_column(String(36), ForeignKey("annotation_sets.id"), index=True)
    frame_index: Mapped[int] = mapped_column(Integer, index=True)
    x_norm: Mapped[float | None] = mapped_column(Float, nullable=True)
    y_norm: Mapped[float | None] = mapped_column(Float, nullable=True)
    visibility: Mapped[str] = mapped_column(String(20), default="visible")  # visible/not_visible/out_of_frame
    provenance: Mapped[str] = mapped_column(String(20), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
