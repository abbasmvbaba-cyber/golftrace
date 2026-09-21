"""
Celery tasks with idempotency, fencing, scratch dirs.
"""
import uuid
from .celery_app import celery_app
from ..db import SessionLocal
from ..services.video_service import prepare_video
from ..services.tracking_service import run_tracking
from ..services.render_service import run_render
from ..services.job_service import get_job, heartbeat_job, complete_job, reconcile_abandoned_jobs
from ..models.job import Job

@celery_app.task(bind=True, name="app.workers.tasks.prepare_video_task", max_retries=3)
def prepare_video_task(self, video_id: str, job_id: str):
    db = SessionLocal()
    try:
        job = get_job(db, job_id)
        if not job:
            return
        worker_id = f"worker-{uuid.uuid4()}"
        # For Celery, we already claimed job in API layer? But we re-claim logic
        # Use fencing token from job
        fencing_token = job.fencing_token
        # Update status to running
        job.status = "running"
        db.commit()
        prepare_video(db, video_id, job_id, worker_id, fencing_token)
    finally:
        db.close()

@celery_app.task(bind=True, name="app.workers.tasks.tracking_task", max_retries=3)
def tracking_task(self, analysis_run_id: str, job_id: str):
    db = SessionLocal()
    try:
        job = get_job(db, job_id)
        if not job:
            return
        worker_id = f"worker-{uuid.uuid4()}"
        fencing_token = job.fencing_token
        job.status = "running"
        db.commit()
        run_tracking(db, analysis_run_id, job_id, worker_id, fencing_token)
    finally:
        db.close()

@celery_app.task(bind=True, name="app.workers.tasks.render_task", max_retries=3)
def render_task(self, render_id: str, job_id: str):
    db = SessionLocal()
    try:
        job = get_job(db, job_id)
        if not job:
            return
        worker_id = f"worker-{uuid.uuid4()}"
        fencing_token = job.fencing_token
        job.status = "running"
        db.commit()
        run_render(db, render_id, job_id, worker_id, fencing_token)
    finally:
        db.close()

@celery_app.task(bind=True, name="app.workers.tasks.cleanup_task")
def cleanup_task(self, project_id: str):
    # Async artifact cleanup for deleted projects
    db = SessionLocal()
    try:
        from ..models.project import Project
        from ..models.video import Video
        from ..core.storage import storage_service
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project or project.status != "deleted":
            return
        videos = db.query(Video).filter(Video.project_id == project_id).all()
        for video in videos:
            # Delete storage keys
            keys = [video.storage_key, video.preview_key, video.thumbnail_key, video.frame_manifest_key]
            for k in keys:
                if k:
                    try:
                        storage_service.delete(k)
                    except:
                        pass
            # Delete track versions, renders
            from ..models.track import TrackVersion, RenderJob
            tracks = db.query(TrackVersion).filter(TrackVersion.video_id == video.id).all()
            for t in tracks:
                try:
                    storage_service.delete(t.storage_key)
                except:
                    pass
            renders = db.query(RenderJob).filter(RenderJob.video_id == video.id).all()
            for r in renders:
                if r.output_storage_key:
                    try:
                        storage_service.delete(r.output_storage_key)
                    except:
                        pass
        # After cleanup, we could hard delete or keep tombstone
        print(f"Cleanup completed for project {project_id}")
    finally:
        db.close()

@celery_app.task(bind=True, name="app.workers.tasks.reconcile_task")
def reconcile_task(self):
    db = SessionLocal()
    try:
        count = reconcile_abandoned_jobs(db)
        print(f"Reconciled {count} abandoned jobs")
    finally:
        db.close()

# Synchronous fallback runners for sandbox/tests without Celery worker
def run_prepare_video_sync(video_id: str, job_id: str):
    db = SessionLocal()
    try:
        job = get_job(db, job_id)
        if not job:
            return
        worker_id = f"sync-worker-{uuid.uuid4()}"
        fencing_token = job.fencing_token
        job.status = "running"
        db.commit()
        prepare_video(db, video_id, job_id, worker_id, fencing_token)
    finally:
        db.close()

def run_tracking_sync(analysis_run_id: str, job_id: str):
    db = SessionLocal()
    try:
        job = get_job(db, job_id)
        if not job:
            return
        worker_id = f"sync-worker-{uuid.uuid4()}"
        fencing_token = job.fencing_token
        job.status = "running"
        db.commit()
        run_tracking(db, analysis_run_id, job_id, worker_id, fencing_token)
    finally:
        db.close()

def run_render_sync(render_id: str, job_id: str):
    db = SessionLocal()
    try:
        job = get_job(db, job_id)
        if not job:
            return
        worker_id = f"sync-worker-{uuid.uuid4()}"
        fencing_token = job.fencing_token
        job.status = "running"
        db.commit()
        run_render(db, render_id, job_id, worker_id, fencing_token)
    finally:
        db.close()
