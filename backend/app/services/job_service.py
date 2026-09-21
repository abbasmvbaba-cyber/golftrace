"""
Job service: atomic claiming, heartbeats, leases, fencing, outbox, reconciler.
"""
import uuid
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_
from ..models.job import Job
from ..models.outbox import OutboxEvent
from ..config import settings

def create_job(db: Session, job_type: str, owner_id: str = None, project_id: str = None, video_id: str = None, idempotency_key: str = None, max_attempts: int = 3) -> Job:
    if not idempotency_key:
        idempotency_key = str(uuid.uuid4())
    # Check existing by idempotency
    existing = db.query(Job).filter(Job.idempotency_key == idempotency_key).first()
    if existing:
        return existing
    job = Job(
        id=str(uuid.uuid4()),
        type=job_type,
        owner_id=owner_id,
        project_id=project_id,
        video_id=video_id,
        status="queued",
        attempt=0,
        max_attempts=max_attempts,
        idempotency_key=idempotency_key,
        fencing_token=str(uuid.uuid4()),
        progress={}
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Outbox event for dispatch
    outbox = OutboxEvent(
        aggregate_type="job",
        aggregate_id=job.id,
        event_type="job_created",
        payload={"job_type": job_type},
        status="pending"
    )
    db.add(outbox)
    db.commit()
    return job

def claim_job(db: Session, worker_id: str, job_types: list) -> Job | None:
    """
    Atomic claiming via SELECT FOR UPDATE SKIP LOCKED (postgres) or simple for sqlite.
    """
    # For postgres, use skip locked; for sqlite, just select first queued
    # We need to handle concurrency
    try:
        # Attempt to use FOR UPDATE SKIP LOCKED if postgres
        if "postgresql" in settings.DATABASE_URL:
            # Raw SQL for atomic claim
            # Find job where status=queued and type in job_types, order by created_at, lock
            job = db.query(Job).filter(
                Job.status == "queued",
                Job.type.in_(job_types)
            ).order_by(Job.created_at).with_for_update(skip_locked=True).first()
        else:
            job = db.query(Job).filter(
                Job.status == "queued",
                Job.type.in_(job_types)
            ).order_by(Job.created_at).first()

        if not job:
            return None

        # Check if already claimed by someone else (lease not expired)
        # Claim
        job.status = "claimed"
        job.claimed_by = worker_id
        job.lease_expires_at = datetime.utcnow() + timedelta(minutes=5)
        job.attempt += 1
        job.fencing_token = str(uuid.uuid4())
        job.started_at = datetime.utcnow()
        db.commit()
        db.refresh(job)
        return job
    except Exception as e:
        db.rollback()
        return None

def heartbeat_job(db: Session, job_id: str, worker_id: str, fencing_token: str, progress: dict = None):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return False
    if job.claimed_by != worker_id or job.fencing_token != fencing_token:
        # Fencing: expired attempt should not commit
        return False
    job.lease_expires_at = datetime.utcnow() + timedelta(minutes=5)
    if progress:
        job.progress = progress
    job.updated_at = datetime.utcnow()
    db.commit()
    return True

def complete_job(db: Session, job_id: str, worker_id: str, fencing_token: str, success: bool, error_code: str = None, error_message: str = None):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return False
    if job.claimed_by != worker_id or job.fencing_token != fencing_token:
        return False
    if success:
        job.status = "succeeded"
    else:
        if job.attempt >= job.max_attempts:
            job.status = "failed"
        else:
            job.status = "queued"
            job.claimed_by = None
            job.lease_expires_at = None
    job.error_code = error_code
    job.error_message = error_message
    job.finished_at = datetime.utcnow()
    db.commit()
    return True

def cancel_job(db: Session, job_id: str, user_id: str) -> bool:
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return False
    if job.owner_id and job.owner_id != user_id:
        return False
    if job.status in ("succeeded","failed","cancelled"):
        return False
    job.status = "cancelled"
    job.finished_at = datetime.utcnow()
    db.commit()
    return True

def reconcile_abandoned_jobs(db: Session):
    """Find jobs with expired lease and re-queue."""
    now = datetime.utcnow()
    abandoned = db.query(Job).filter(
        Job.status.in_(("claimed","running")),
        Job.lease_expires_at != None,
        Job.lease_expires_at < now
    ).all()
    for job in abandoned:
        if job.attempt >= job.max_attempts:
            job.status = "failed"
            job.error_code = "LEASE_EXPIRED"
            job.error_message = "Job abandoned, lease expired"
        else:
            job.status = "queued"
            job.claimed_by = None
            job.lease_expires_at = None
        job.updated_at = now
    db.commit()
    return len(abandoned)

def get_job(db: Session, job_id: str):
    return db.query(Job).filter(Job.id == job_id).first()
