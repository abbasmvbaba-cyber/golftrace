from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ...db import get_db
from ...models.track import TrackVersion, AnalysisRun
from ...models.video import Video
from ...models.user import User
from ...models.annotation import AnnotationSet, Annotation
from ...core.auth import require_user
from ...core.security import check_video_ownership
from ...schemas.track import TrackVersionResponse, TrackDataResponse, TrackRevisionCreate
from ...core.storage import storage_service
import json
import uuid

router = APIRouter()

@router.get("/videos/{video_id}/tracks", response_model=list[TrackVersionResponse])
def list_tracks(video_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    video = check_video_ownership(video_id, user.id, db)
    tracks = db.query(TrackVersion).filter(TrackVersion.video_id == video_id).order_by(TrackVersion.created_at.desc()).all()
    return tracks

@router.get("/tracks/{track_version_id}", response_model=TrackDataResponse)
def get_track(track_version_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    track = db.query(TrackVersion).filter(TrackVersion.id == track_version_id).first()
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    if track.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        data = storage_service.get_bytes(track.storage_key)
        artifact = json.loads(data)
        points = artifact.get("points", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load track: {e}")

    return TrackDataResponse(
        track_version=TrackVersionResponse.model_validate(track),
        points=points
    )

@router.post("/tracks/{track_version_id}/revisions", response_model=TrackVersionResponse, status_code=201)
def create_revision(track_version_id: str, payload: TrackRevisionCreate, db: Session = Depends(get_db), user: User = Depends(require_user)):
    orig_track = db.query(TrackVersion).filter(TrackVersion.id == track_version_id).first()
    if not orig_track:
        raise HTTPException(status_code=404, detail="Track not found")
    if orig_track.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    video = db.query(Video).filter(Video.id == orig_track.video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Check idempotency via job table? For simplicity check existing track with same parent and reason? We'll skip and create new

    # Load original artifact to get existing points
    try:
        orig_data = storage_service.get_bytes(orig_track.storage_key)
        orig_artifact = json.loads(orig_data)
    except:
        orig_artifact = {"points": []}

    # Build new annotations from payload.annotations
    # Payload.annotations is list of dicts with frame_index, x_norm, y_norm, visibility
    # We need to create a new annotation set? For manual revision, we directly create new track version

    # For simplicity, we will create a new track version that merges original with new annotations
    # Load original points map
    orig_points_map = {p["frame_index"]: p for p in orig_artifact.get("points", [])}

    # Apply revisions
    for ann in payload.annotations:
        fi = ann.get("frame_index")
        if fi is None:
            continue
        # Validate
        vis = ann.get("visibility", "visible")
        x = ann.get("x_norm")
        y = ann.get("y_norm")
        if vis == "visible" and (x is None or y is None):
            raise HTTPException(status_code=400, detail="Visible must have coords")
        if vis != "visible" and (x is not None or y is not None):
            raise HTTPException(status_code=400, detail="Non-visible must have null coords")

        # Create new point
        # Need pts_us from manifest or original
        pts_us = orig_points_map.get(fi, {}).get("pts_us", fi*33333)
        new_point = {
            "frame_index": fi,
            "pts_us": pts_us,
            "x_norm": x,
            "y_norm": y,
            "provenance": "manual",
            "visibility": vis,
            "score": 1.0,
            "is_anchor": True
        }
        orig_points_map[fi] = new_point

    # Now we have updated map, need to apply gap policy again to interpolate?
    from ...tracking.interfaces import TrackPoint
    from ...tracking.gap_policy import GapPolicy
    from ...config import settings

    track_points = []
    for fi in sorted(orig_points_map.keys()):
        p = orig_points_map[fi]
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

    # For manual revision, we should also fill missing frames in interval? We need analysis interval from original video? We'll assume we keep same interval as before
    # For simplicity, we apply gap policy with default max_gap
    gap_policy = GapPolicy(max_gap_ms=settings.DEFAULT_MAX_GAP_MS)
    display_track = gap_policy.apply(track_points)

    artifact = {
        "schema_version": 1,
        "video_id": video.id,
        "parent_track_version_id": orig_track.id,
        "points": [p.to_dict() for p in display_track],
        "raw_points": [p.to_dict() for p in track_points],
        "provenance_summary": {
            "total": len(display_track),
            "manual": sum(1 for p in display_track if p.provenance=="manual"),
            "interpolated": sum(1 for p in display_track if p.provenance=="interpolated"),
            "missing": sum(1 for p in display_track if p.x_norm is None)
        }
    }

    new_key = f"projects/{video.project_id}/videos/{video.id}/tracks/{uuid.uuid4()}.json"
    storage_service.put_bytes(new_key, json.dumps(artifact).encode('utf-8'), content_type="application/json")

    new_track = TrackVersion(
        id=str(uuid.uuid4()),
        video_id=video.id,
        parent_id=orig_track.id,
        owner_id=user.id,
        storage_key=new_key,
        schema_version=1,
        frame_count=len(display_track),
        provenance_summary=artifact["provenance_summary"],
        is_manual=True
    )
    db.add(new_track)
    db.commit()
    db.refresh(new_track)
    return new_track
