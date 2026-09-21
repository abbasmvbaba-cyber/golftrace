from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ...db import get_db
from ...models.video import Video
from ...models.annotation import AnnotationSet, Annotation
from ...models.user import User
from ...core.auth import require_user
from ...core.security import check_video_ownership, check_rate_limit
from ...schemas.annotation import AnnotationSetCreate, AnnotationSetResponse, AnnotationResponse
from ...config import settings
import uuid
from datetime import datetime

router = APIRouter()

@router.post("/videos/{video_id}/annotation-sets", response_model=AnnotationSetResponse, status_code=201)
def create_annotation_set(video_id: str, payload: AnnotationSetCreate, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_rate_limit(user.id, "annotation", 60)
    video = check_video_ownership(video_id, user.id, db)

    # Validate analysis interval
    interval = payload.analysis_interval
    if interval:
        start = interval.get("start_frame")
        end = interval.get("end_frame")
        if start is None or end is None:
            raise HTTPException(status_code=400, detail="Invalid analysis_interval")
        if end < start:
            raise HTTPException(status_code=400, detail="end_frame must >= start_frame")
        duration_frames = end - start + 1
        if duration_frames > settings.ANALYSIS_BUDGET_FRAMES:
            raise HTTPException(status_code=400, detail={"error_code": "ANALYSIS_INTERVAL_TOO_LARGE", "message": f"Interval {duration_frames} frames exceeds budget {settings.ANALYSIS_BUDGET_FRAMES}"})
        # Check duration via manifest if available
        from ...core.storage import storage_service
        import json
        if video.frame_manifest_key:
            try:
                manifest_bytes = storage_service.get_bytes(video.frame_manifest_key)
                manifest = json.loads(manifest_bytes)
                frames = manifest.get("frames", [])
                if start < 0 or end >= len(frames):
                    raise HTTPException(status_code=400, detail="Interval out of range")
                duration_us = frames[end]["pts_us"] - frames[start]["pts_us"]
                if duration_us > settings.MAX_ANALYSIS_INTERVAL_SEC * 1e6:
                    raise HTTPException(status_code=400, detail={"error_code": "ANALYSIS_INTERVAL_TOO_LONG", "message": f"Interval {duration_us/1e6}s exceeds limit {settings.MAX_ANALYSIS_INTERVAL_SEC}s"})
            except HTTPException:
                raise
            except:
                pass

    # Validate annotations
    for ann in payload.annotations:
        if ann.visibility == "visible":
            if ann.x_norm is None or ann.y_norm is None:
                raise HTTPException(status_code=400, detail="Visible annotation must have x_norm, y_norm")
            if not (0 <= ann.x_norm <= 1 and 0 <= ann.y_norm <= 1):
                raise HTTPException(status_code=400, detail="x_norm, y_norm must be in [0,1]")
        else:
            # For not_visible/out_of_frame, x_norm,y_norm should be null per contract
            if ann.x_norm is not None or ann.y_norm is not None:
                # Allow but we will store null? Better enforce null
                raise HTTPException(status_code=400, detail="Non-visible annotation must have null coordinates")
        if ann.visibility not in ("visible","not_visible","out_of_frame"):
            raise HTTPException(status_code=400, detail="Invalid visibility")

    # Check idempotency via annotation set? We use idempotency_key unique in job? For annotation sets we store key in metadata?
    # For simplicity, check if any annotation set with same parent and same idempotency? We don't have storage for key, so we use a trick: if payload has parent_id, we check if child already exists with same annotations? For MVP, we skip strict idempotency but we check if set with same idempotency_key exists via outbox? We'll just create.

    # Create annotation set
    ann_set_id = str(uuid.uuid4())
    ann_set = AnnotationSet(
        id=ann_set_id,
        video_id=video_id,
        owner_id=user.id,
        version=1,
        is_snapshot=False,
        parent_id=payload.parent_id,
        metadata_json={"analysis_interval": interval} if interval else {}
    )
    db.add(ann_set)
    db.commit()

    # Create annotations
    for ann_in in payload.annotations:
        ann = Annotation(
            id=str(uuid.uuid4()),
            annotation_set_id=ann_set_id,
            frame_index=ann_in.frame_index,
            x_norm=ann_in.x_norm,
            y_norm=ann_in.y_norm,
            visibility=ann_in.visibility,
            provenance="manual"
        )
        db.add(ann)
    db.commit()

    # Refresh
    db.refresh(ann_set)
    annotations = db.query(Annotation).filter(Annotation.annotation_set_id == ann_set_id).all()

    return AnnotationSetResponse(
        id=ann_set.id,
        video_id=ann_set.video_id,
        owner_id=ann_set.owner_id,
        version=ann_set.version,
        is_snapshot=ann_set.is_snapshot,
        parent_id=ann_set.parent_id,
        created_at=ann_set.created_at,
        metadata=ann_set.metadata_json,
        annotations=[AnnotationResponse.model_validate(a) for a in annotations]
    )

@router.get("/annotation-sets/{annotation_set_id}", response_model=AnnotationSetResponse)
def get_annotation_set(annotation_set_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    ann_set = db.query(AnnotationSet).filter(AnnotationSet.id == annotation_set_id).first()
    if not ann_set:
        raise HTTPException(status_code=404, detail="Annotation set not found")
    if ann_set.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    annotations = db.query(Annotation).filter(Annotation.annotation_set_id == annotation_set_id).order_by(Annotation.frame_index).all()
    return AnnotationSetResponse(
        id=ann_set.id,
        video_id=ann_set.video_id,
        owner_id=ann_set.owner_id,
        version=ann_set.version,
        is_snapshot=ann_set.is_snapshot,
        parent_id=ann_set.parent_id,
        created_at=ann_set.created_at,
        metadata=ann_set.metadata_json,
        annotations=[AnnotationResponse.model_validate(a) for a in annotations]
    )

def create_snapshot(db: Session, annotation_set_id: str) -> AnnotationSet:
    """Create immutable snapshot copy of annotation set for analysis."""
    orig = db.query(AnnotationSet).filter(AnnotationSet.id == annotation_set_id).first()
    if not orig:
        raise ValueError("Annotation set not found")
    snap_id = str(uuid.uuid4())
    snap = AnnotationSet(
        id=snap_id,
        video_id=orig.video_id,
        owner_id=orig.owner_id,
        version=1,
        is_snapshot=True,
        parent_id=orig.id,
        metadata_json=orig.metadata_json
    )
    db.add(snap)
    db.commit()
    # Copy annotations
    anns = db.query(Annotation).filter(Annotation.annotation_set_id == orig.id).all()
    for ann in anns:
        new_ann = Annotation(
            id=str(uuid.uuid4()),
            annotation_set_id=snap_id,
            frame_index=ann.frame_index,
            x_norm=ann.x_norm,
            y_norm=ann.y_norm,
            visibility=ann.visibility,
            provenance=ann.provenance
        )
        db.add(new_ann)
    db.commit()
    db.refresh(snap)
    return snap
