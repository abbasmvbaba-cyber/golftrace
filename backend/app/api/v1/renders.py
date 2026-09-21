from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ...db import get_db
from ...models.track import TrackVersion, RenderJob
from ...models.video import Video
from ...models.user import User
from ...core.auth import require_user
from ...core.security import check_video_ownership, validate_style, check_rate_limit
from ...schemas.render import RenderCreate, RenderResponse, RenderDownloadResponse
from ...services.job_service import create_job
from ...core.storage import storage_service
from ...config import settings
from datetime import datetime, timedelta
import uuid

router = APIRouter()

@router.post("/tracks/{track_version_id}/renders", response_model=RenderResponse, status_code=202)
def create_render(track_version_id: str, payload: RenderCreate, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_rate_limit(user.id, "render", 10)
    track = db.query(TrackVersion).filter(TrackVersion.id == track_version_id).first()
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    if track.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    video = db.query(Video).filter(Video.id == track.video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Validate style
    validate_style(payload.style)

    # Validate export params
    export = payload.export or {}
    width = export.get("width", settings.MAX_EXPORT_WIDTH)
    height = export.get("height", settings.MAX_EXPORT_HEIGHT)
    fps = export.get("fps", 30)

    if width > settings.MAX_EXPORT_WIDTH or height > settings.MAX_EXPORT_HEIGHT:
        raise HTTPException(status_code=400, detail=f"Export resolution exceeds limit {settings.MAX_EXPORT_WIDTH}x{settings.MAX_EXPORT_HEIGHT}")
    if fps > settings.MAX_EXPORT_FPS:
        raise HTTPException(status_code=400, detail=f"FPS exceeds limit {settings.MAX_EXPORT_FPS}")
    if width % 2 != 0 or height % 2 != 0:
        raise HTTPException(status_code=400, detail="Export width/height must be even")

    # Idempotency check
    from ...models.job import Job
    existing_job = db.query(Job).filter(Job.idempotency_key == payload.idempotency_key).first()
    if existing_job:
        existing_render = db.query(RenderJob).filter(RenderJob.job_id == existing_job.id).first()
        if existing_render:
            return existing_render

    # Create render job
    render_id = str(uuid.uuid4())
    style_snapshot = payload.style.copy()
    style_snapshot["export"] = {"width": width, "height": height, "fps": fps}

    render = RenderJob(
        id=render_id,
        track_version_id=track_version_id,
        owner_id=user.id,
        video_id=video.id,
        style_snapshot=style_snapshot,
        status="queued"
    )
    db.add(render)
    db.commit()

    job = create_job(db, "rendering", owner_id=user.id, project_id=video.project_id, video_id=video.id, idempotency_key=payload.idempotency_key)
    render.job_id = job.id
    db.commit()
    db.refresh(render)

    # Dispatch
    from ...workers.tasks import render_task, run_render_sync
    try:
        render_task.delay(render.id, job.id)
    except Exception as e:
        print(f"Celery render dispatch failed {e}, sync fallback")
        run_render_sync(render.id, job.id)

    return render

@router.get("/renders/{render_id}", response_model=RenderResponse)
def get_render(render_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    render = db.query(RenderJob).filter(RenderJob.id == render_id).first()
    if not render:
        raise HTTPException(status_code=404, detail="Render not found")
    if render.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return render

@router.get("/renders/{render_id}/download", response_model=RenderDownloadResponse)
def get_download_url(render_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    render = db.query(RenderJob).filter(RenderJob.id == render_id).first()
    if not render:
        raise HTTPException(status_code=404, detail="Render not found")
    if render.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if render.status != "succeeded" or not render.output_storage_key:
        raise HTTPException(status_code=400, detail="Render not ready")

    url = storage_service.generate_presigned_url(render.output_storage_key, expiry_sec=settings.SIGNED_URL_EXPIRY_SEC)
    expires_at = datetime.utcnow() + timedelta(seconds=settings.SIGNED_URL_EXPIRY_SEC)
    return RenderDownloadResponse(url=url, expires_at=expires_at)
