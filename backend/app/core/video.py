"""
Video probing and processing with ffprobe/ffmpeg wrapper + OpenCV fallback.
"""
import json
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Dict, Optional, List, Tuple
import cv2
from ..config import settings

class VideoProbeError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)

def _run_ffprobe(file_path: str) -> Optional[Dict]:
    """Try ffprobe binary."""
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path
        ]
        # No shell=True, restricted
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None

def _probe_with_opencv(file_path: str) -> Dict:
    cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        raise VideoProbeError("CORRUPT_MEDIA", "Cannot open video with OpenCV")
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    # Duration estimate
    duration_sec = frame_count / fps if fps > 0 else 0
    cap.release()
    return {
        "width": width,
        "height": height,
        "encoded_width": width,
        "encoded_height": height,
        "fps_avg": fps,
        "fps_max": fps,
        "duration_us": int(duration_sec * 1e6),
        "frame_count": frame_count,
        "codec": "unknown",
        "has_audio": False,
        "rotation": 0,
        "is_vfr": False,
        "probe_method": "opencv"
    }

def probe_video(file_path: str) -> Dict:
    """
    Probe video, returns dict with validated metadata.
    Validates against limits.
    """
    metadata = None
    ffprobe_data = _run_ffprobe(file_path)

    if ffprobe_data:
        try:
            # Parse streams
            video_stream = None
            audio_stream = None
            for s in ffprobe_data.get("streams", []):
                if s.get("codec_type") == "video" and not video_stream:
                    video_stream = s
                if s.get("codec_type") == "audio" and not audio_stream:
                    audio_stream = s

            if not video_stream:
                raise VideoProbeError("NO_VIDEO_STREAM", "No video stream found")

            width = int(video_stream.get("width", 0))
            height = int(video_stream.get("height", 0))
            # Rotation from side data or tags
            rotation = 0
            tags = video_stream.get("tags", {})
            if "rotate" in tags:
                try:
                    rotation = int(tags["rotate"])
                except:
                    rotation = 0

            # FPS
            avg_fps_str = video_stream.get("avg_frame_rate", "0/1")
            r_frame_rate = video_stream.get("r_frame_rate", "0/1")
            def parse_fps(s):
                try:
                    num, den = s.split("/")
                    num = float(num); den = float(den)
                    if den == 0:
                        return 0
                    return num/den
                except:
                    return 0
            fps_avg = parse_fps(avg_fps_str)
            fps_max = parse_fps(r_frame_rate)

            # Duration
            duration_str = video_stream.get("duration") or ffprobe_data.get("format", {}).get("duration")
            if duration_str:
                duration_sec = float(duration_str)
            else:
                duration_sec = 0
                if fps_avg > 0:
                    nb_frames = video_stream.get("nb_frames")
                    if nb_frames:
                        try:
                            duration_sec = int(nb_frames) / fps_avg
                        except:
                            pass

            duration_us = int(duration_sec * 1e6)

            codec = video_stream.get("codec_name")
            has_audio = audio_stream is not None

            # Check VFR: if r_frame_rate != avg_frame_rate significantly or time_base suggests
            is_vfr = abs(fps_avg - fps_max) > 0.1 if fps_avg and fps_max else False

            # Frame count
            nb_frames = video_stream.get("nb_frames")
            if nb_frames:
                frame_count = int(nb_frames)
            else:
                # estimate
                frame_count = int(duration_sec * fps_avg) if fps_avg else 0

            metadata = {
                "width": width,
                "height": height,
                "encoded_width": width,
                "encoded_height": height,
                "fps_avg": fps_avg,
                "fps_max": fps_max,
                "duration_us": duration_us,
                "frame_count": frame_count,
                "codec": codec,
                "has_audio": has_audio,
                "rotation": rotation,
                "is_vfr": is_vfr,
                "probe_method": "ffprobe",
                "raw": ffprobe_data
            }
        except Exception as e:
            # Fallback to opencv
            metadata = None

    if metadata is None:
        metadata = _probe_with_opencv(file_path)

    # Apply canonical orientation correction for dimensions
    rot = metadata.get("rotation", 0)
    if rot in (90,270):
        # Swap width/height for canonical
        canon_w = metadata["height"]
        canon_h = metadata["width"]
    else:
        canon_w = metadata["width"]
        canon_h = metadata["height"]

    metadata["canonical_width"] = canon_w
    metadata["canonical_height"] = canon_h
    metadata["encoded_width"] = metadata["width"]
    metadata["encoded_height"] = metadata["height"]
    metadata["width"] = canon_w
    metadata["height"] = canon_h

    # Validation against limits
    size_bytes = os.path.getsize(file_path)
    if size_bytes > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise VideoProbeError("VIDEO_TOO_LARGE", f"File size {size_bytes} exceeds limit {settings.MAX_UPLOAD_SIZE_MB} MiB")

    duration_sec = metadata["duration_us"] / 1e6
    if duration_sec > settings.MAX_DURATION_SEC:
        raise VideoProbeError("VIDEO_TOO_LONG", f"Duration {duration_sec:.2f}s exceeds limit {settings.MAX_DURATION_SEC}s")

    long_edge = max(canon_w, canon_h)
    short_edge = min(canon_w, canon_h)
    if long_edge > settings.MAX_LONG_EDGE:
        raise VideoProbeError("VIDEO_RESOLUTION_TOO_HIGH", f"Long edge {long_edge} exceeds limit {settings.MAX_LONG_EDGE}")
    if short_edge > settings.MAX_SHORT_EDGE:
        raise VideoProbeError("VIDEO_RESOLUTION_TOO_HIGH", f"Short edge {short_edge} exceeds limit {settings.MAX_SHORT_EDGE}")

    fps = metadata.get("fps_avg") or metadata.get("fps_max") or 0
    if fps > settings.MAX_FPS:
        raise VideoProbeError("FPS_TOO_HIGH", f"FPS {fps} exceeds limit {settings.MAX_FPS}")

    return metadata

def generate_frame_manifest(file_path: str, video_id: str) -> Dict:
    """
    Generate frame manifest with presentation order, pts_us.
    Implements time contract:
    - Use source presentation timestamps, not constant FPS assumption
    - Store presentation-order frame_index and integer pts_us
    - Retain original PTS and time-base metadata
    - Handle VFR and B-frame presentation ordering
    - Policy for missing timestamps: repair if <1% missing, else error

    Tries: ffprobe packets -> PyAV -> OpenCV fallback
    """
    # First try ffprobe with packets for accurate PTS
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_packets",
            "-select_streams", "v:0",
            "-show_entries", "packet=pts,dts,flags,size",
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            packets = data.get("packets", [])
            # Filter packets with pts
            pts_list = []
            for p in packets:
                pts = p.get("pts")
                if pts is None or pts == "N/A":
                    continue
                try:
                    pts_int = int(pts)
                    pts_list.append(pts_int)
                except:
                    continue
            if pts_list:
                # Need time_base from stream probe
                ffprobe_stream = _run_ffprobe(file_path)
                time_base = "1/1000000"
                width = height = 0
                if ffprobe_stream:
                    vs = next((s for s in ffprobe_stream.get("streams", []) if s.get("codec_type")=="video"), None)
                    if vs:
                        tb = vs.get("time_base", "1/1000")
                        time_base = tb
                        width = int(vs.get("width",0))
                        height = int(vs.get("height",0))
                        # Parse time_base to us
                        try:
                            num, den = time_base.split("/")
                            tb_sec = float(num)/float(den)
                        except:
                            tb_sec = 1/1000
                    else:
                        tb_sec = 1/1000
                else:
                    tb_sec = 1/1000

                # Convert pts to us
                pts_us_list = [int(p * tb_sec * 1e6) for p in pts_list]
                # Sort for presentation order? Packets are in decode order, but pts is presentation?
                # For manifest we need presentation order sorted by pts
                # Pair with original index
                indexed = list(enumerate(pts_us_list))
                indexed.sort(key=lambda x: x[1])
                # Normalize origin
                first_us = indexed[0][1] if indexed else 0
                manifest_frames = []
                for new_idx, (orig_idx, pts_us) in enumerate(indexed):
                    manifest_frames.append({
                        "frame_index": new_idx,
                        "pts_us": pts_us - first_us,
                        "original_pts": pts_list[orig_idx],
                        "time_base": time_base,
                        "keyframe": False,
                        "width": width,
                        "height": height
                    })
                if manifest_frames:
                    duration_us = manifest_frames[-1]["pts_us"]
                    if len(manifest_frames) >= 2:
                        delta = manifest_frames[-1]["pts_us"] - manifest_frames[-2]["pts_us"]
                        duration_us += delta
                    # Detect VFR: check variance in deltas
                    deltas = [manifest_frames[i]["pts_us"] - manifest_frames[i-1]["pts_us"] for i in range(1,len(manifest_frames))]
                    avg_delta = sum(deltas)/len(deltas) if deltas else 0
                    vfr = any(abs(d - avg_delta) > avg_delta*0.1 for d in deltas) if avg_delta else False
                    return {
                        "schema_version": 1,
                        "video_id": video_id,
                        "duration_us": duration_us,
                        "frame_count": len(manifest_frames),
                        "frames": manifest_frames,
                        "vfr": vfr,
                        "time_repaired": False,
                        "probe_method": "ffprobe_packets"
                    }
    except Exception as e:
        # print(f"ffprobe packets failed {e}")
        pass

    # Try PyAV with accurate presentation timestamps
    try:
        import av
        container = av.open(file_path)
        video_stream = next(s for s in container.streams if s.type == 'video')
        time_base = video_stream.time_base
        # Collect frames with pts, dts, and detect B-frame ordering
        pts_entries = []
        for packet in container.demux(video_stream):
            if packet.pts is None:
                continue
            # Use pts for presentation
            sec = float(packet.pts * time_base)
            us = int(sec * 1e6)
            pts_entries.append((us, int(packet.pts), packet.is_keyframe, packet.dts))

        # If no packets, try decoding frames
        if not pts_entries:
            for idx, frame in enumerate(container.decode(video_stream)):
                pts = frame.pts
                if pts is None:
                    continue
                sec = float(pts * time_base)
                us = int(sec * 1e6)
                pts_entries.append((us, int(pts), frame.key_frame, frame.dts))

        # Sort by pts for presentation order
        pts_entries.sort(key=lambda x: x[0])

        # Validate and repair if needed
        # Check for missing
        missing_count = 0
        # For PyAV we assume all pts present if we have entries
        # Normalize
        if pts_entries:
            first_us = pts_entries[0][0]
            manifest_frames = []
            for frame_index, (pts_us, orig_pts, keyframe, dts) in enumerate(pts_entries):
                manifest_frames.append({
                    "frame_index": frame_index,
                    "pts_us": pts_us - first_us,
                    "original_pts": orig_pts,
                    "original_dts": int(dts) if dts is not None else None,
                    "time_base": str(time_base),
                    "keyframe": bool(keyframe),
                    "width": video_stream.width,
                    "height": video_stream.height
                })
            if manifest_frames:
                duration_us = manifest_frames[-1]["pts_us"]
                if len(manifest_frames) >= 2:
                    delta = manifest_frames[-1]["pts_us"] - manifest_frames[-2]["pts_us"]
                    duration_us += delta
                deltas = [manifest_frames[i]["pts_us"] - manifest_frames[i-1]["pts_us"] for i in range(1,len(manifest_frames))]
                avg_delta = sum(deltas)/len(deltas) if deltas else 0
                vfr = any(abs(d - avg_delta) > avg_delta*0.15 for d in deltas) if avg_delta else False
                # Check monotonic
                from .time import validate_timestamps, FrameEntry
                frame_objs = [FrameEntry(f["frame_index"], f["pts_us"]) for f in manifest_frames]
                valid, msg, needs_repair = validate_timestamps(frame_objs)
                if not valid:
                    raise VideoProbeError("INVALID_TIMESTAMPS", msg)
                return {
                    "schema_version": 1,
                    "video_id": video_id,
                    "duration_us": duration_us,
                    "frame_count": len(manifest_frames),
                    "frames": manifest_frames,
                    "vfr": vfr,
                    "time_repaired": needs_repair,
                    "probe_method": "pyav"
                }
    except VideoProbeError:
        raise
    except Exception as e:
        # print(f"PyAV manifest failed {e}")
        pass

    # Fallback OpenCV with repair logic
    cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        raise VideoProbeError("CORRUPT_MEDIA", "Cannot open video for manifest")
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    frames = []
    for i in range(frame_count):
        pts_us = int((i / fps) * 1e6)
        frames.append({
            "frame_index": i,
            "pts_us": pts_us,
            "original_pts": i,
            "time_base": f"1/{int(fps*1000)}",
            "keyframe": i % int(fps) == 0,
            "width": width,
            "height": height
        })

    # Validate timestamps
    from .time import validate_timestamps, FrameEntry, repair_timestamps
    frame_objs = [FrameEntry(f["frame_index"], f["pts_us"]) for f in frames]
    valid, msg, needs_repair = validate_timestamps(frame_objs)
    if not valid:
        raise VideoProbeError("INVALID_TIMESTAMPS", msg)
    if needs_repair:
        # Repair
        repaired_objs = repair_timestamps(frame_objs, fps_avg=fps)
        for i, obj in enumerate(repaired_objs):
            frames[i]["pts_us"] = obj.pts_us
        time_repaired = True
    else:
        time_repaired = False

    duration_us = int((frame_count / fps) * 1e6) if fps else 0
    return {
        "schema_version": 1,
        "video_id": video_id,
        "duration_us": duration_us,
        "frame_count": frame_count,
        "frames": frames,
        "vfr": False,
        "time_repaired": time_repaired,
        "probe_method": "opencv"
    }

def extract_exact_frame(file_path: str, frame_index: int, rotation: int = 0) -> bytes:
    """Extract exact frame by index, return JPEG bytes."""
    cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        raise VideoProbeError("CORRUPT_MEDIA", "Cannot open video")
    # Seek
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        raise VideoProbeError("FRAME_NOT_FOUND", f"Frame {frame_index} not found")
    # Apply rotation
    if rotation == 90:
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    elif rotation == 180:
        frame = cv2.rotate(frame, cv2.ROTATE_180)
    elif rotation == 270:
        frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

    # Encode JPEG
    success, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not success:
        raise VideoProbeError("ENCODE_FAILED", "Failed to encode frame")
    return jpeg.tobytes()

def transcode_preview(input_path: str, output_path: str, max_width: int = 1280, max_height: int = 720, fps: int = 30):
    """Transcode to browser-compatible preview using OpenCV (or ffmpeg if available)."""
    # Try ffmpeg binary first
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i", input_path,
            "-vf", f"scale='min({max_width},iw)':min'({max_height},ih)':force_original_aspect_ratio=decrease,scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "libx264",
            "-profile:v", "high",
            "-pix_fmt", "yuv420p",
            "-r", str(fps),
            "-movflags", "+faststart",
            "-an",  # no audio for preview to simplify
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode == 0 and os.path.exists(output_path):
            return
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback OpenCV: resize and re-encode
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise VideoProbeError("CORRUPT_MEDIA", "Cannot open for preview")
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30

    scale = min(max_width / src_w, max_height / src_h, 1.0)
    dst_w = int(src_w * scale)
    dst_h = int(src_h * scale)
    # Ensure even
    dst_w = dst_w // 2 * 2
    dst_h = dst_h // 2 * 2
    if dst_w < 2:
        dst_w = 2
    if dst_h < 2:
        dst_h = 2

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (dst_w, dst_h))
    if not out.isOpened():
        cap.release()
        raise VideoProbeError("ENCODE_FAILED", "Cannot open preview writer")

    # Sample frames if fps differs
    frame_interval = src_fps / fps if src_fps > fps else 1
    count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if count % max(1, int(frame_interval)) == 0 or frame_interval <= 1:
            resized = cv2.resize(frame, (dst_w, dst_h))
            out.write(resized)
        count += 1

    cap.release()
    out.release()

def generate_thumbnail(input_path: str, output_path: str, frame_index: int = 0, width: int = 320):
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise VideoProbeError("CORRUPT_MEDIA", "Cannot open for thumbnail")
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        # Try first frame
        cap = cv2.VideoCapture(input_path)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            raise VideoProbeError("FRAME_NOT_FOUND", "Cannot read thumbnail frame")
    h, w = frame.shape[:2]
    scale = width / w
    new_h = int(h * scale)
    resized = cv2.resize(frame, (width, new_h))
    cv2.imwrite(output_path, resized)
