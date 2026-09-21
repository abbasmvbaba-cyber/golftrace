"""
Video service: handling preparation jobs, manifest, preview, thumbnails.
"""
import os
import json
import tempfile
from pathlib import Path
from sqlalchemy.orm import Session
from ..models.video import Video, FrameManifest
from ..models.job import Job
from ..core.storage import storage_service
from ..core.video import probe_video, generate_frame_manifest, transcode_preview, generate_thumbnail, VideoProbeError
from ..config import settings
import uuid

def prepare_video(db: Session, video_id: str, job_id: str, worker_id: str, fencing_token: str):
    from .job_service import heartbeat_job, complete_job
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        complete_job(db, job_id, worker_id, fencing_token, False, "VIDEO_NOT_FOUND", "Video not found")
        return

    # Check project deleted
    from ..models.project import Project
    project = db.query(Project).filter(Project.id == video.project_id).first()
    if project and project.status == "deleted":
        complete_job(db, job_id, worker_id, fencing_token, False, "PROJECT_DELETED", "Project deleted")
        return

    try:
        video.preparation_status = "probing"
        db.commit()
        heartbeat_job(db, job_id, worker_id, fencing_token, {"stage": "probing", "progress": 10})

        # Download original to temp
        temp_dir = tempfile.mkdtemp()
        temp_input = os.path.join(temp_dir, "input.mp4")
        try:
            storage_service.get_file(video.storage_key, temp_input)
        except FileNotFoundError:
            raise VideoProbeError("FILE_NOT_FOUND", "Original file not found in storage")

        # Probe
        metadata = probe_video(temp_input)

        video.duration_us = metadata["duration_us"]
        video.width = metadata["width"]
        video.height = metadata["height"]
        video.encoded_width = metadata["encoded_width"]
        video.encoded_height = metadata["encoded_height"]
        video.rotation = metadata["rotation"]
        video.fps_avg = metadata["fps_avg"]
        video.fps_max = metadata["fps_max"]
        video.is_vfr = metadata["is_vfr"]
        video.codec = metadata["codec"]
        video.has_audio = metadata["has_audio"]
        video.probe_metadata = metadata
        db.commit()

        heartbeat_job(db, job_id, worker_id, fencing_token, {"stage": "manifest", "progress": 40})
        video.preparation_status = "manifesting"
        db.commit()

        # Generate manifest
        manifest = generate_frame_manifest(temp_input, video.id)
        manifest_json = json.dumps(manifest).encode('utf-8')
        manifest_key = f"projects/{video.project_id}/videos/{video.id}/manifest/{uuid.uuid4()}.json"
        storage_service.put_bytes(manifest_key, manifest_json, content_type="application/json")

        # Save manifest record
        fm = FrameManifest(
            id=str(uuid.uuid4()),
            video_id=video.id,
            storage_key=manifest_key,
            schema_version=1,
            frame_count=manifest["frame_count"],
            duration_us=manifest["duration_us"],
            vfr=manifest.get("vfr", False)
        )
        db.add(fm)
        video.frame_manifest_key = manifest_key
        db.commit()

        heartbeat_job(db, job_id, worker_id, fencing_token, {"stage": "preview", "progress": 70})
        video.preparation_status = "previewing"
        db.commit()

        # Preview
        temp_preview = os.path.join(temp_dir, "preview.mp4")
        transcode_preview(temp_input, temp_preview, max_width=1280, max_height=720, fps=30)
        preview_key = f"projects/{video.project_id}/videos/{video.id}/preview/{uuid.uuid4()}.mp4"
        storage_service.put_file(preview_key, temp_preview, content_type="video/mp4")
        video.preview_key = preview_key
        db.commit()

        # Thumbnail
        temp_thumb = os.path.join(temp_dir, "thumb.jpg")
        generate_thumbnail(temp_input, temp_thumb, frame_index=0, width=320)
        thumb_key = f"projects/{video.project_id}/videos/{video.id}/thumb/{uuid.uuid4()}.jpg"
        storage_service.put_file(thumb_key, temp_thumb, content_type="image/jpeg")
        video.thumbnail_key = thumb_key
        db.commit()

        video.preparation_status = "ready"
        db.commit()

        heartbeat_job(db, job_id, worker_id, fencing_token, {"stage": "done", "progress": 100})
        complete_job(db, job_id, worker_id, fencing_token, True)

    except VideoProbeError as e:
        video.preparation_status = "failed"
        video.preparation_error = f"{e.code}: {e.message}"
        db.commit()
        complete_job(db, job_id, worker_id, fencing_token, False, e.code, e.message)
    except Exception as e:
        video.preparation_status = "failed"
        video.preparation_error = str(e)
        db.commit()
        complete_job(db, job_id, worker_id, fencing_token, False, "PREPARATION_FAILED", str(e))
    finally:
        # Cleanup temp
        try:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
        except:
            pass
