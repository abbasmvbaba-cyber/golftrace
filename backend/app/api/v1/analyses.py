from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ...db import get_db
from ...models.video import Video
from ...models.annotation import AnnotationSet
from ...models.track import AnalysisRun
from ...models.user import User
from ...core.auth import require_user
from ...core.security import check_video_ownership, check_rate_limit
from ...schemas.analysis import AnalysisCreate, AnalysisResponse
from ...services.job_service import create_job
from ...api.v1.annotations import create_snapshot
import uuid

router = APIRouter()

@router.post("/videos/{video_id}/analyses", response_model=AnalysisResponse, status_code=202)
def create_analysis(video_id: str, payload: AnalysisCreate, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_rate_limit(user.id, "analysis", 10)
    video = check_video_ownership(video_id, user.id, db)

    if video.preparation_status != "ready":
        raise HTTPException(status_code=400, detail="Video not ready")

    # Validate annotation set
    ann_set = db.query(AnnotationSet).filter(AnnotationSet.id == payload.annotation_set_id).first()
    if not ann_set:
        raise HTTPException(status_code=404, detail="Annotation set not found")
    if ann_set.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if ann_set.video_id != video_id:
        raise HTTPException(status_code=400, detail="Annotation set does not belong to this video")

    # Check engine
    if payload.engine not in ("classical","model"):
        raise HTTPException(status_code=400, detail="Invalid engine")

    if payload.engine == "model":
        # Check if model available
        from ...tracking.interfaces import ModelAdapterInterface
        # For now, model not available, return explicit error
        raise HTTPException(status_code=400, detail={"error_code": "MODEL_NOT_AVAILABLE", "message": "Model adapter not configured, use classical or manual workflow"})

    # Idempotency: check existing analysis with same key
    from ...models.job import Job
    existing_job = db.query(Job).filter(Job.idempotency_key == payload.idempotency_key).first()
    if existing_job:
        # Find analysis linked to this job
        existing_analysis = db.query(AnalysisRun).filter(AnalysisRun.job_id == existing_job.id).first()
        if existing_analysis:
            return existing_analysis

    # Create snapshot
    snapshot = create_snapshot(db, payload.annotation_set_id)

    # Validate analysis interval budget
    interval = snapshot.metadata_json.get("analysis_interval") if snapshot.metadata_json else None
    if interval:
        start = interval.get("start_frame", 0)
        end = interval.get("end_frame", 0)
        if (end - start + 1) > 1800:  # use settings
            raise HTTPException(status_code=400, detail="Analysis budget exceeded")

    # Create analysis run
    analysis_id = str(uuid.uuid4())
    engine_config = payload.engine_config or {}
    # Default max_gap_ms
    if "max_gap_ms" not in engine_config:
        from ...config import settings
        engine_config["max_gap_ms"] = settings.DEFAULT_MAX_GAP_MS

    analysis = AnalysisRun(
        id=analysis_id,
        video_id=video_id,
        annotation_set_snapshot_id=snapshot.id,
        owner_id=user.id,
        engine=payload.engine,
        engine_config=engine_config,
        code_version="0.1.0",  # Should be git commit or version
        status="queued"
    )
    db.add(analysis)
    db.commit()

    # Create job
    job = create_job(db, "tracking", owner_id=user.id, project_id=video.project_id, video_id=video.id, idempotency_key=payload.idempotency_key)
    analysis.job_id = job.id
    db.commit()
    db.refresh(analysis)

    # Dispatch
    from ...workers.tasks import tracking_task, run_tracking_sync
    try:
        tracking_task.delay(analysis.id, job.id)
    except Exception as e:
        print(f"Celery tracking dispatch failed {e}, sync fallback")
        run_tracking_sync(analysis.id, job.id)

    return analysis

@router.get("/analyses/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(analysis_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    analysis = db.query(AnalysisRun).filter(AnalysisRun.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return analysis
