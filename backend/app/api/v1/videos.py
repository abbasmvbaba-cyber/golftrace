from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from ...db import get_db
from ...models.video import Video
from ...models.user import User
from ...core.auth import require_user
from ...core.security import check_video_ownership
from ...core.storage import storage_service
from ...schemas.video import VideoResponse, PlaybackResponse
from ...config import settings
from datetime import datetime, timedelta
import json

router = APIRouter()

@router.get("/{video_id}", response_model=VideoResponse)
def get_video(video_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    video = check_video_ownership(video_id, user.id, db)
    return video

@router.get("/{video_id}/playback", response_model=PlaybackResponse)
def get_playback(video_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    video = check_video_ownership(video_id, user.id, db)
    # Prefer preview if ready, else original
    key = video.preview_key if video.preview_key and video.preparation_status == "ready" else video.storage_key
    if not key:
        raise HTTPException(status_code=404, detail="No playback available")
    url = storage_service.generate_presigned_url(key, expiry_sec=settings.SIGNED_URL_EXPIRY_SEC)
    expires_at = datetime.utcnow() + timedelta(seconds=settings.SIGNED_URL_EXPIRY_SEC)
    return PlaybackResponse(url=url, expires_at=expires_at)

@router.get("/{video_id}/frame-manifest")
def get_frame_manifest(video_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    video = check_video_ownership(video_id, user.id, db)
    if not video.frame_manifest_key:
        raise HTTPException(status_code=404, detail="Manifest not ready")
    try:
        data = storage_service.get_bytes(video.frame_manifest_key)
        manifest = json.loads(data)
        return manifest
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Manifest file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{video_id}/frames/{frame_index}")
def get_exact_frame(video_id: str, frame_index: int, format: str = "jpeg", quality: int = 95, db: Session = Depends(get_db), user: User = Depends(require_user)):
    video = check_video_ownership(video_id, user.id, db)
    if video.preparation_status != "ready":
        raise HTTPException(status_code=400, detail="Video not ready")
    # Validate frame_index
    # Load manifest to check range
    try:
        manifest_data = storage_service.get_bytes(video.frame_manifest_key)
        manifest = json.loads(manifest_data)
        frame_count = manifest.get("frame_count", 0)
        if frame_index < 0 or frame_index >= frame_count:
            raise HTTPException(status_code=404, detail="Frame index out of range")
    except:
        # If manifest not available, still allow but check via video probe? For now skip
        pass

    # Download original to temp and extract frame
    import tempfile, os
    temp_dir = tempfile.mkdtemp()
    temp_input = os.path.join(temp_dir, "input.mp4")
    try:
        storage_service.get_file(video.storage_key, temp_input)
        from ...core.video import extract_exact_frame
        jpeg_bytes = extract_exact_frame(temp_input, frame_index, rotation=video.rotation)
        # Return as image/jpeg
        return Response(content=jpeg_bytes, media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract frame: {e}")
    finally:
        try:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
        except:
            pass

@router.post("/{video_id}/tracks", response_model=dict)
def create_manual_track_endpoint(video_id: str, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """
    Create manual track from annotation set.
    Body: {annotation_set_id, idempotency_key}
    """
    from ...models.annotation import AnnotationSet
    from ...services.tracking_service import create_manual_track
    from ...schemas.track import TrackVersionResponse
    video = check_video_ownership(video_id, user.id, db)
    annotation_set_id = payload.get("annotation_set_id")
    if not annotation_set_id:
        raise HTTPException(status_code=400, detail="annotation_set_id required")
    ann_set = db.query(AnnotationSet).filter(AnnotationSet.id == annotation_set_id).first()
    if not ann_set or ann_set.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Annotation set not found")
    try:
        track_version = create_manual_track(db, video_id, annotation_set_id, user.id)
        return {"track_version_id": track_version.id, "track_version": TrackVersionResponse.model_validate(track_version).model_dump()}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# Internal storage serving for local fallback
@router.get("/internal-storage/{key_path:path}")
def internal_storage(key_path: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    # This endpoint serves local storage files when S3 presigned URLs fallback to internal path
    # We need to check ownership: key_path contains project_id, so we can extract and check
    # For simplicity, check if user owns any video with this key
    # This is not perfect but for local dev it's okay
    # In production, this endpoint should not be used when S3 is configured
    from ...models.video import Video
    from ...models.track import TrackVersion, RenderJob
    # Try to find video containing key
    # For security, we check if key contains user's project
    # We'll search
    # This is a bit expensive but okay for local
    videos = db.query(Video).filter(Video.owner_id == user.id).all()
    allowed = False
    for v in videos:
        if v.storage_key == key_path or v.preview_key == key_path or v.thumbnail_key == key_path or v.frame_manifest_key == key_path:
            allowed = True
            break
    if not allowed:
        # Check tracks
        tracks = db.query(TrackVersion).filter(TrackVersion.owner_id == user.id).all()
        for t in tracks:
            if t.storage_key == key_path:
                allowed = True
                break
    if not allowed:
        renders = db.query(RenderJob).filter(RenderJob.owner_id == user.id).all()
        for r in renders:
            if r.output_storage_key == key_path:
                allowed = True
                break

    if not allowed:
        raise HTTPException(status_code=403, detail="Access denied to storage key")

    try:
        data = storage_service.get_bytes(key_path)
        # Guess content type
        if key_path.endswith(".mp4"):
            media_type = "video/mp4"
        elif key_path.endswith(".json"):
            media_type = "application/json"
        elif key_path.endswith(".jpg") or key_path.endswith(".jpeg"):
            media_type = "image/jpeg"
        else:
            media_type = "application/octet-stream"
        return Response(content=data, media_type=media_type)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
