"""
Security helpers: quotas, rate limiting (simple in-memory), ownership checks.
"""
from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session
from ..db import get_db
from ..models.project import Project
from ..models.video import Video
from ..config import settings
import time
from collections import defaultdict

# Simple in-memory rate limiter (per user per endpoint)
_rate_limit_store = defaultdict(list)

def check_rate_limit(user_id: str, key: str, limit: int, window_sec: int = 60):
    # Use Redis-backed rate limiter with fallback
    from .rate_limit import rate_limiter
    return rate_limiter.check(user_id, key, limit, window_sec)

def check_project_ownership(project_id: str, user_id: str, db: Session):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    if project.status == "deleted":
        raise HTTPException(status_code=410, detail="Project deleted")
    return project

def check_video_ownership(video_id: str, user_id: str, db: Session):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    # Also check project not deleted
    project = db.query(Project).filter(Project.id == video.project_id).first()
    if project and project.status == "deleted":
        raise HTTPException(status_code=410, detail="Project deleted")
    return video

def check_quotas(user_id: str, db: Session):
    # Project count
    count = db.query(Project).filter(Project.owner_id == user_id, Project.status == "active").count()
    if count >= settings.MAX_PROJECTS_PER_USER:
        raise HTTPException(status_code=403, detail="Project quota exceeded")

    # Storage quota (sum video sizes)
    from sqlalchemy import func
    from ..models.video import Video
    total = db.query(func.sum(Video.size_bytes)).filter(Video.owner_id == user_id).scalar() or 0
    max_bytes = settings.MAX_STORAGE_PER_USER_GB * 1024**3
    if total >= max_bytes:
        raise HTTPException(status_code=403, detail="Storage quota exceeded")

def validate_style(style: dict):
    """Validate and bound style parameters."""
    errors = []
    # color hex
    color = style.get("color", "#FF0000")
    if not isinstance(color, str) or not color.startswith("#") or len(color) not in (4,7,9):
        errors.append("invalid color")

    stroke = style.get("stroke_width_norm", 0.005)
    if not (0.0001 <= stroke <= 0.05):
        errors.append("stroke_width_norm out of bounds [0.0001,0.05]")

    opacity = style.get("opacity", 1.0)
    if not (0 <= opacity <= 1):
        errors.append("opacity out of bounds")

    trail = style.get("trail_duration_ms", 2000)
    if not (0 <= trail <= 10000):
        errors.append("trail_duration_ms out of bounds")

    # glow
    glow = style.get("glow", False)
    if not isinstance(glow, bool):
        errors.append("glow must be bool")

    # head marker
    head = style.get("head_marker", "circle")
    if head not in ("none","circle","dot"):
        errors.append("head_marker invalid")

    if errors:
        raise HTTPException(status_code=400, detail={"error_code": "INVALID_STYLE", "errors": errors})

    return True
