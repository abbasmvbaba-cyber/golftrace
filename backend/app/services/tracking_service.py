"""
Tracking service: orchestrates classical tracker.
"""
import os
import json
import tempfile
import cv2
from sqlalchemy.orm import Session
from ..models.video import Video
from ..models.annotation import AnnotationSet, Annotation
from ..models.track import AnalysisRun, TrackVersion
from ..models.job import Job
from ..core.storage import storage_service
from ..tracking.classical_detector import ClassicalDetector
from ..tracking.camera_motion import CameraMotionEstimator
from ..tracking.tracker import TemporalTracker
from ..tracking.gap_policy import DisplayPathGenerator
from ..tracking.interfaces import FrameData, Candidate, TrackPoint
from ..config import settings
import uuid
from datetime import datetime

def _load_manifest(manifest_key: str) -> dict:
    data = storage_service.get_bytes(manifest_key)
    return json.loads(data)

def _get_frame_source(video_path: str, manifest: dict, analysis_interval: dict = None):
    """
    Returns list of FrameData for analysis interval.
    analysis_interval: {start_frame, end_frame} inclusive
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError("Cannot open video for tracking")

    frames_data = manifest.get("frames", [])
    # Filter by interval
    start = analysis_interval.get("start_frame", 0) if analysis_interval else 0
    end = analysis_interval.get("end_frame", len(frames_data)-1) if analysis_interval else len(frames_data)-1

    # Validate budget
    if (end - start + 1) > settings.ANALYSIS_BUDGET_FRAMES:
        raise ValueError(f"Analysis interval {end-start+1} exceeds budget {settings.ANALYSIS_BUDGET_FRAMES}")

    if (end - start + 1) * 1e6 / 1e6 > settings.MAX_ANALYSIS_INTERVAL_SEC * 60:  # Simplified check using frame count * avg fps?
        # Actually check duration via pts
        if frames_data:
            duration_us = frames_data[end]["pts_us"] - frames_data[start]["pts_us"]
            if duration_us > settings.MAX_ANALYSIS_INTERVAL_SEC * 1e6:
                raise ValueError(f"Analysis interval duration {duration_us/1e6}s exceeds limit {settings.MAX_ANALYSIS_INTERVAL_SEC}s")

    result = []
    for fi in range(start, end+1):
        if fi >= len(frames_data):
            break
        cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
        ret, frame = cap.read()
        if not ret:
            continue
        # For canonical, we need rotation handling? For simplicity assume already canonical (we would rotate if needed)
        # Get pts
        pts_us = frames_data[fi]["pts_us"]
        # Use frame as canonical (if rotation, rotate)
        # We'll handle rotation from video metadata outside

        # Determine canonical dimensions from manifest? Use frame shape
        h,w = frame.shape[:2]
        fd = FrameData(frame_index=fi, pts_us=pts_us, image=frame, canonical_width=w, canonical_height=h)
        result.append(fd)

    cap.release()
    return result

def run_tracking(db: Session, analysis_run_id: str, job_id: str, worker_id: str, fencing_token: str):
    from .job_service import heartbeat_job, complete_job
    analysis = db.query(AnalysisRun).filter(AnalysisRun.id == analysis_run_id).first()
    if not analysis:
        complete_job(db, job_id, worker_id, fencing_token, False, "ANALYSIS_NOT_FOUND", "Analysis run not found")
        return

    video = db.query(Video).filter(Video.id == analysis.video_id).first()
    if not video:
        complete_job(db, job_id, worker_id, fencing_token, False, "VIDEO_NOT_FOUND", "Video not found")
        return

    try:
        analysis.status = "running"
        db.commit()
        heartbeat_job(db, job_id, worker_id, fencing_token, {"stage": "loading", "progress": 5})

        # Load annotation snapshot
        ann_set = db.query(AnnotationSet).filter(AnnotationSet.id == analysis.annotation_set_snapshot_id).first()
        if not ann_set:
            raise ValueError("Annotation snapshot not found")

        annotations = db.query(Annotation).filter(Annotation.annotation_set_id == ann_set.id).all()
        # Build anchor map
        anchor_map = {}
        for ann in annotations:
            if ann.visibility == "visible" and ann.x_norm is not None:
                tp = TrackPoint(frame_index=ann.frame_index, pts_us=0, x_norm=ann.x_norm, y_norm=ann.y_norm,
                                provenance="manual", visibility="visible", score=1.0, is_anchor=True)
            else:
                tp = TrackPoint(frame_index=ann.frame_index, pts_us=0, x_norm=None, y_norm=None,
                                provenance="manual", visibility=ann.visibility, score=None, is_anchor=True)
            anchor_map[ann.frame_index] = tp

        # Get analysis interval from metadata
        interval = ann_set.metadata_json.get("analysis_interval") if ann_set.metadata_json else None
        if not interval:
            # Default to all frames or first 15s?
            interval = {"start_frame": 0, "end_frame": 100}

        # Download video
        temp_dir = tempfile.mkdtemp()
        temp_input = os.path.join(temp_dir, "input.mp4")
        storage_service.get_file(video.storage_key, temp_input)

        # Load manifest
        manifest = _load_manifest(video.frame_manifest_key) if video.frame_manifest_key else {"frames": []}

        # If manifest empty, generate quick one?
        if not manifest.get("frames"):
            # Fallback
            cap = cv2.VideoCapture(temp_input)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            cap.release()
            manifest["frames"] = [{"frame_index": i, "pts_us": int(i/fps*1e6)} for i in range(frame_count)]

        heartbeat_job(db, job_id, worker_id, fencing_token, {"stage": "frames", "progress": 20})

        frames = _get_frame_source(temp_input, manifest, interval)

        # Update pts_us in anchor_map from frames
        frame_pts_map = {f.frame_index: f.pts_us for f in frames}
        for fi, tp in anchor_map.items():
            if fi in frame_pts_map:
                tp.pts_us = frame_pts_map[fi]

        heartbeat_job(db, job_id, worker_id, fencing_token, {"stage": "camera_motion", "progress": 40})

        # Camera motion estimation
        cam_estimator = CameraMotionEstimator(model=settings.CAMERA_MODEL)
        camera_motion = cam_estimator.estimate(frames)

        heartbeat_job(db, job_id, worker_id, fencing_token, {"stage": "detection", "progress": 60})

        # Candidate detection
        detector = ClassicalDetector()
        candidates = {}
        for f in frames:
            # Define ROI: if we have Kalman prediction, use bounded local search
            # For first pass, no ROI, full frame
            # For subsequent, we could use previous track? But we do detection first for all frames
            cands = detector.detect(f, roi=None, camera_transform=None)
            candidates[f.frame_index] = cands

        heartbeat_job(db, job_id, worker_id, fencing_token, {"stage": "tracking", "progress": 80})

        # Temporal tracker
        tracker = TemporalTracker()
        config = analysis.engine_config or {}
        raw_track = tracker.track(frames, candidates, anchor_map, camera_motion, config)

        # Gap policy and display path
        max_gap_ms = config.get("max_gap_ms", settings.DEFAULT_MAX_GAP_MS)
        display_gen = DisplayPathGenerator(max_gap_ms=max_gap_ms, artistic_extension=False)
        display_track = display_gen.generate(raw_track, camera_motion, config)

        # Save track artifact
        track_artifact = {
            "schema_version": 1,
            "video_id": video.id,
            "analysis_run_id": analysis.id,
            "points": [p.to_dict() for p in display_track],
            "raw_points": [p.to_dict() for p in raw_track],
            "camera_motion": {
                "segments": camera_motion.segments,
                "quality": camera_motion.quality
                # Transforms not stored as full matrix for size? Store as list
            },
            "gap_policy": {"max_gap_ms": max_gap_ms},
            "provenance_summary": {
                "total": len(display_track),
                "detected": sum(1 for p in display_track if p.provenance=="detected"),
                "manual": sum(1 for p in display_track if p.provenance=="manual"),
                "interpolated": sum(1 for p in display_track if p.provenance=="interpolated"),
                "predicted": sum(1 for p in display_track if p.provenance=="predicted"),
                "missing": sum(1 for p in display_track if p.x_norm is None)
            }
        }

        # Store artifact
        track_key = f"projects/{video.project_id}/videos/{video.id}/tracks/{uuid.uuid4()}.json"
        storage_service.put_bytes(track_key, json.dumps(track_artifact).encode('utf-8'), content_type="application/json")

        # Create track version
        track_version = TrackVersion(
            id=str(uuid.uuid4()),
            video_id=video.id,
            analysis_run_id=analysis.id,
            owner_id=analysis.owner_id,
            storage_key=track_key,
            schema_version=1,
            frame_count=len(display_track),
            provenance_summary=track_artifact["provenance_summary"],
            is_manual=False
        )
        db.add(track_version)
        db.commit()
        db.refresh(track_version)

        analysis.track_version_id = track_version.id
        analysis.status = "succeeded"
        db.commit()

        heartbeat_job(db, job_id, worker_id, fencing_token, {"stage": "done", "progress": 100})
        complete_job(db, job_id, worker_id, fencing_token, True)

    except Exception as e:
        import traceback
        traceback.print_exc()
        analysis.status = "failed"
        db.commit()
        complete_job(db, job_id, worker_id, fencing_token, False, "TRACKING_FAILED", str(e))
    finally:
        try:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
        except:
            pass

def create_manual_track(db: Session, video_id: str, annotation_set_id: str, owner_id: str) -> TrackVersion:
    """
    Generate explicitly manual or interpolated display path from manual annotations.
    """
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise ValueError("Video not found")

    ann_set = db.query(AnnotationSet).filter(AnnotationSet.id == annotation_set_id).first()
    annotations = db.query(Annotation).filter(Annotation.annotation_set_id == annotation_set_id).order_by(Annotation.frame_index).all()

    # Load manifest for pts
    manifest = _load_manifest(video.frame_manifest_key) if video.frame_manifest_key else {"frames": []}
    pts_map = {f["frame_index"]: f["pts_us"] for f in manifest.get("frames", [])}

    track_points = []
    for ann in annotations:
        pts_us = pts_map.get(ann.frame_index, ann.frame_index * 33333)
        tp = TrackPoint(
            frame_index=ann.frame_index,
            pts_us=pts_us,
            x_norm=ann.x_norm,
            y_norm=ann.y_norm,
            provenance="manual",
            visibility=ann.visibility,
            score=1.0,
            is_anchor=True
        )
        track_points.append(tp)

    # If analysis interval defined, we need to fill gaps via interpolation up to max_gap_ms
    # Use gap policy
    from ..tracking.gap_policy import GapPolicy
    # For manual, we interpolate inside interval regardless of gap? But spec says default max auto interpolation gap 100ms, long gaps require user review
    # We'll use same policy
    gap_policy = GapPolicy(max_gap_ms=settings.DEFAULT_MAX_GAP_MS)
    # Need to sort
    track_points_sorted = sorted(track_points, key=lambda p: p.frame_index)

    # For manual workflow, we also need to generate interpolated points between manual anchors if gap <= max_gap
    # The gap policy already does that, but it expects track covering all frames. We need to create placeholder for missing frames in interval
    # Determine interval
    interval = ann_set.metadata_json.get("analysis_interval") if ann_set.metadata_json and ann_set.metadata_json.get("analysis_interval") else None
    if interval:
        start = interval.get("start_frame", 0)
        end = interval.get("end_frame", start)
        # Create full list with missing for frames without annotation
        full_track = []
        ann_map = {tp.frame_index: tp for tp in track_points_sorted}
        for fi in range(start, end+1):
            if fi in ann_map:
                full_track.append(ann_map[fi])
            else:
                pts_us = pts_map.get(fi, fi*33333)
                full_track.append(TrackPoint(frame_index=fi, pts_us=pts_us, x_norm=None, y_norm=None, provenance="predicted", visibility="not_visible"))
        # Apply gap policy
        display_track = gap_policy.apply(full_track)
    else:
        display_track = track_points_sorted

    artifact = {
        "schema_version": 1,
        "video_id": video_id,
        "points": [p.to_dict() for p in display_track],
        "raw_points": [p.to_dict() for p in track_points_sorted],
        "gap_policy": {"max_gap_ms": settings.DEFAULT_MAX_GAP_MS},
        "provenance_summary": {
            "total": len(display_track),
            "manual": sum(1 for p in display_track if p.provenance=="manual"),
            "interpolated": sum(1 for p in display_track if p.provenance=="interpolated"),
            "missing": sum(1 for p in display_track if p.x_norm is None)
        }
    }

    track_key = f"projects/{video.project_id}/videos/{video_id}/tracks/{uuid.uuid4()}.json"
    storage_service.put_bytes(track_key, json.dumps(artifact).encode('utf-8'), content_type="application/json")

    tv = TrackVersion(
        id=str(uuid.uuid4()),
        video_id=video_id,
        owner_id=owner_id,
        storage_key=track_key,
        schema_version=1,
        frame_count=len(display_track),
        provenance_summary=artifact["provenance_summary"],
        is_manual=True
    )
    db.add(tv)
    db.commit()
    db.refresh(tv)
    return tv
