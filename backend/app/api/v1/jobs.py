from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ...db import get_db
from ...models.job import Job
from ...models.user import User
from ...core.auth import require_user
from ...schemas.job import JobResponse
from ...services.job_service import cancel_job, get_job

router = APIRouter()

@router.get("/{job_id}", response_model=JobResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    job = get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.owner_id and job.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return job

@router.post("/{job_id}/cancel")
def cancel(job_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    success = cancel_job(db, job_id, user.id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel job")
    return {"status": "cancelled", "job_id": job_id}
