"""
Render service.
"""
import os
import json
import tempfile
from sqlalchemy.orm import Session
from ..models.track import TrackVersion, RenderJob
from ..models.video import Video
from ..core.storage import storage_service
from ..tracking.renderer import VideoRenderer
from ..config import settings
import uuid

def run_render(db: Session, render_id: str, job_id: str, worker_id: str, fencing_token: str):
    from .job_service import heartbeat_job, complete_job
    render = db.query(RenderJob).filter(RenderJob.id == render_id).first()
    if not render:
        complete_job(db, job_id, worker_id, fencing_token, False, "RENDER_NOT_FOUND", "Render job not found")
        return

    video = db.query(Video).filter(Video.id == render.video_id).first()
    track_version = db.query(TrackVersion).filter(TrackVersion.id == render.track_version_id).first()

    if not video or not track_version:
        complete_job(db, job_id, worker_id, fencing_token, False, "NOT_FOUND", "Video or track not found")
        return

    try:
        render.status = "running"
        db.commit()
        heartbeat_job(db, job_id, worker_id, fencing_token, {"stage": "loading", "progress": 10})

        # Download video and track
        temp_dir = tempfile.mkdtemp()
        temp_input = os.path.join(temp_dir, "input.mp4")
        temp_output = os.path.join(temp_dir, "output.mp4")

        storage_service.get_file(video.storage_key, temp_input)

        track_data = storage_service.get_bytes(track_version.storage_key)
        track_artifact = json.loads(track_data)
        points = track_artifact.get("points", [])

        from ..tracking.interfaces import TrackPoint
        track_points = []
        for p in points:
            tp = TrackPoint(
                frame_index=p["frame_index"],
                pts_us=p["pts_us"],
                x_norm=p["x_norm"],
                y_norm=p["y_norm"],
                provenance=p["provenance"],
                visibility=p["visibility"],
                score=p.get("score"),
                is_anchor=p.get("is_anchor", False)
            )
            track_points.append(tp)

        # Load manifest for VFR handling
        manifest = {}
        if video.frame_manifest_key:
            try:
                manifest_bytes = storage_service.get_bytes(video.frame_manifest_key)
                manifest = json.loads(manifest_bytes)
            except:
                manifest = {}

        heartbeat_job(db, job_id, worker_id, fencing_token, {"stage": "rendering", "progress": 50})

        style = render.style_snapshot or {}
        export_cfg = style.get("export", {}) or {}
        # Merge export defaults
        export_cfg = {
            "width": export_cfg.get("width", settings.MAX_EXPORT_WIDTH),
            "height": export_cfg.get("height", settings.MAX_EXPORT_HEIGHT),
            "fps": export_cfg.get("fps", 30)
        }

        renderer = VideoRenderer(style=style, export_config=export_cfg)
        renderer.render(temp_input, track_points, temp_output, manifest)

        # Verify output
        if not os.path.exists(temp_output) or os.path.getsize(temp_output) == 0:
            raise RuntimeError("Render produced empty file")

        # Probe output
        from ..core.video import probe_video
        try:
            out_meta = probe_video(temp_output)
        except Exception as e:
            # If probe fails, still try to publish but log
            out_meta = {"width": export_cfg["width"], "height": export_cfg["height"], "duration_us": 0}

        heartbeat_job(db, job_id, worker_id, fencing_token, {"stage": "uploading", "progress": 90})

        # Upload to unique key
        output_key = f"projects/{video.project_id}/videos/{video.id}/renders/{render.id}/{uuid.uuid4()}.mp4"
        storage_service.put_file(output_key, temp_output, content_type="video/mp4")

        render.output_storage_key = output_key
        render.output_metadata = {
            "width": out_meta.get("width"),
            "height": out_meta.get("height"),
            "duration_us": out_meta.get("duration_us"),
            "codec": out_meta.get("codec"),
            "fps": out_meta.get("fps_avg")
        }
        render.status = "succeeded"
        db.commit()

        heartbeat_job(db, job_id, worker_id, fencing_token, {"stage": "done", "progress": 100})
        complete_job(db, job_id, worker_id, fencing_token, True)

    except Exception as e:
        import traceback
        traceback.print_exc()
        render.status = "failed"
        db.commit()
        complete_job(db, job_id, worker_id, fencing_token, False, "RENDER_FAILED", str(e))
    finally:
        try:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
        except:
            pass
