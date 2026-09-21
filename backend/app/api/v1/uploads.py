from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from sqlalchemy.orm import Session
from ...db import get_db
from ...models.project import Project
from ...models.upload_session import UploadSession
from ...models.video import Video
from ...models.user import User
from ...core.auth import require_user
from ...core.security import check_project_ownership, check_rate_limit
from ...schemas.upload import UploadCreate, UploadResponse, UploadCompleteRequest, UploadCompleteResponse
from ...core.storage import storage_service
from ...config import settings, max_upload_bytes
from ...services.job_service import create_job
import uuid
from datetime import datetime, timedelta

router = APIRouter()

@router.post("/projects/{project_id}/uploads", response_model=UploadResponse)
def create_upload_session(project_id: str, payload: UploadCreate, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_rate_limit(user.id, "upload", 5)
    project = check_project_ownership(project_id, user.id, db)

    if payload.size_bytes > max_upload_bytes():
        raise HTTPException(status_code=400, detail={"error_code": "VIDEO_TOO_LARGE", "message": f"File too large, limit {settings.MAX_UPLOAD_SIZE_MB} MiB"})

    # Check idempotency
    existing = db.query(UploadSession).filter(UploadSession.idempotency_key == payload.idempotency_key).first()
    if existing:
        return UploadResponse(
            upload_id=existing.id,
            upload_url=existing.upload_url,
            storage_key=existing.storage_key,
            expires_at=existing.expires_at
        )

    storage_key = f"projects/{project_id}/videos/original/{uuid.uuid4()}_{payload.filename}"
    upload_id = str(uuid.uuid4())

    # For S3, generate presigned PUT URL; for local fallback, return direct upload endpoint
    upload_url = None
    if storage_service.use_s3 and storage_service.s3_client:
        try:
            upload_url = storage_service.s3_client.generate_presigned_url(
                'put_object',
                Params={'Bucket': settings.S3_BUCKET, 'Key': storage_key, 'ContentType': payload.content_type or 'video/mp4'},
                ExpiresIn=3600
            )
        except Exception:
            upload_url = f"/api/v1/uploads/{upload_id}/direct-upload"
    else:
        upload_url = f"/api/v1/uploads/{upload_id}/direct-upload"

    session = UploadSession(
        id=upload_id,
        project_id=project_id,
        owner_id=user.id,
        filename=payload.filename,
        size_bytes=payload.size_bytes,
        storage_key=storage_key,
        status="created",
        upload_url=upload_url,
        idempotency_key=payload.idempotency_key,
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return UploadResponse(
        upload_id=session.id,
        upload_url=session.upload_url,
        storage_key=session.storage_key,
        expires_at=session.expires_at
    )

@router.post("/uploads/{upload_id}/direct-upload")
async def direct_upload(upload_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    # For local fallback, accept raw bytes upload
    session = db.query(UploadSession).filter(UploadSession.id == upload_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Upload session not found")
    if session.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if session.status == "completed":
        return {"status": "already_completed"}

    # Read body
    data = await request.body()
    if len(data) > max_upload_bytes():
        raise HTTPException(status_code=400, detail="Too large")

    storage_service.put_bytes(session.storage_key, data, content_type="video/mp4")
    session.status = "uploading"
    db.commit()
    return {"status": "uploaded", "size": len(data)}

@router.post("/uploads/{upload_id}/complete", response_model=UploadCompleteResponse)
def complete_upload(upload_id: str, payload: UploadCompleteRequest, db: Session = Depends(get_db), user: User = Depends(require_user)):
    session = db.query(UploadSession).filter(UploadSession.id == upload_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Upload session not found")
    if session.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    if session.status == "completed" and session.video_id:
        # Idempotent
        video = db.query(Video).filter(Video.id == session.video_id).first()
        if video:
            # Find job for this video? Look up job by video_id
            from ...models.job import Job
            job = db.query(Job).filter(Job.video_id == video.id).order_by(Job.created_at.desc()).first()
            return UploadCompleteResponse(video_id=video.id, job_id=job.id if job else "")

    # Verify actual object size
    try:
        actual_size = storage_service.get_size(session.storage_key)
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail={"error_code": "UPLOAD_NOT_FOUND", "message": "Uploaded file not found, please upload again"})

    if payload.size_bytes and abs(actual_size - payload.size_bytes) > 1024:
        # Allow small diff
        pass

    if actual_size > max_upload_bytes():
        raise HTTPException(status_code=400, detail={"error_code": "VIDEO_TOO_LARGE", "message": "File too large"})

    # Create video record
    video_id = str(uuid.uuid4())
    video = Video(
        id=video_id,
        project_id=session.project_id,
        owner_id=user.id,
        original_filename=session.filename,
        storage_key=session.storage_key,
        size_bytes=actual_size,
        preparation_status="pending"
    )
    db.add(video)
    session.video_id = video_id
    session.status = "completed"
    db.commit()
    db.refresh(video)

    # Create preparation job
    job = create_job(db, "video_preparation", owner_id=user.id, project_id=session.project_id, video_id=video.id, idempotency_key=f"prep-{video.id}")

    # Dispatch
    from ...workers.tasks import prepare_video_task, run_prepare_video_sync
    try:
        # Try Celery
        prepare_video_task.delay(video.id, job.id)
    except Exception as e:
        print(f"Celery dispatch failed {e}, running sync fallback")
        # Synchronous fallback for sandbox/tests
        run_prepare_video_sync(video.id, job.id)

    return UploadCompleteResponse(video_id=video.id, job_id=job.id)
