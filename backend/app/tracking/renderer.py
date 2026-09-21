"""
Renderer: decode and process frames in streaming pipeline, map timestamps, respect gaps, render tracer.
Produces MP4 with H264 yuv420p, faststart, AAC when needed.
"""
import cv2
import numpy as np
import os
import json
import subprocess
from typing import List, Dict
from .interfaces import TrackPoint
from ..core.geometry import canonical_to_export, transform_point
import tempfile

def _ensure_even(n: int) -> int:
    return n // 2 * 2

class VideoRenderer:
    def __init__(self, style: Dict, export_config: Dict):
        self.style = style
        self.export_config = export_config

    def render(self, input_video_path: str, track: List[TrackPoint], output_path: str, manifest: Dict):
        """
        Render tracer onto video.
        input_video_path: source video
        track: list of TrackPoint sorted by frame_index
        output_path: output MP4 path
        manifest: frame manifest dict
        """
        # Validate style
        from ..core.security import validate_style
        validate_style(self.style)

        # Export config
        export_w = self.export_config.get("width", 1920)
        export_h = self.export_config.get("height", 1080)
        export_fps = self.export_config.get("fps", 30)

        export_w = _ensure_even(export_w)
        export_h = _ensure_even(export_h)

        # Style params
        color_hex = self.style.get("color", "#FF0000")
        # Parse hex to BGR
        def hex_to_bgr(h):
            h = h.lstrip("#")
            if len(h) == 6:
                r = int(h[0:2], 16)
                g = int(h[2:4], 16)
                b = int(h[4:6], 16)
            elif len(h) == 3:
                r = int(h[0]*2, 16)
                g = int(h[1]*2, 16)
                b = int(h[2]*2, 16)
            else:
                r,g,b = 255,0,0
            return (b,g,r)
        color_bgr = hex_to_bgr(color_hex)
        stroke_norm = self.style.get("stroke_width_norm", 0.005)
        stroke_px = max(1, int(stroke_norm * export_h))
        glow = self.style.get("glow", False)
        glow_radius = int(self.style.get("glow_radius_norm", 0.01) * export_h) if glow else 0
        opacity = self.style.get("opacity", 1.0)
        trail_ms = self.style.get("trail_duration_ms", 2000)
        fade = self.style.get("fade", True)
        head_marker = self.style.get("head_marker", "circle")
        progressive = self.style.get("progressive_reveal", True)
        inferred_style = self.style.get("inferred_style", "dashed")
        audio_preserve = self.style.get("audio_preserve", True)

        # Build track map frame_index -> point
        track_map = {tp.frame_index: tp for tp in track}

        # Open input
        cap = cv2.VideoCapture(input_video_path)
        if not cap.isOpened():
            raise RuntimeError("Cannot open input video")

        src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        src_fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Determine output fps: if export_fps None, use src_fps capped
        if export_fps is None:
            export_fps = min(src_fps, 60)

        # For VFR input, we need to map output timestamps to source timestamps
        # For simplicity, we will read all frames and write at export_fps, but respect source pts
        # We'll use manifest to get pts_us

        # Create temp video without audio first
        temp_video_path = output_path + ".temp.mp4"
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        # We'll try to use avc1 if available
        # Try mp4v, fallback
        out = cv2.VideoWriter(temp_video_path, fourcc, export_fps, (export_w, export_h))
        if not out.isOpened():
            # Try other codec
            fourcc = cv2.VideoWriter_fourcc(*'avc1')
            out = cv2.VideoWriter(temp_video_path, fourcc, export_fps, (export_w, export_h))
            if not out.isOpened():
                cap.release()
                raise RuntimeError("Cannot open output writer")

        # For progressive reveal and trail, we need to keep history
        # trail duration in frames
        trail_frames = int((trail_ms / 1000.0) * export_fps) if trail_ms > 0 else frame_count

        # For each output frame, we need to find source frame
        # If input and output fps differ, we need to map
        # Simplest: if src_fps approx export_fps, 1:1
        # For VFR, use manifest pts

        frames_manifest = manifest.get("frames", []) if manifest else []
        # Build pts list
        pts_list = [f["pts_us"] for f in frames_manifest] if frames_manifest else []

        # For rendering, we will iterate over source frames and write each as output frame (if fps matches)
        # If export_fps differs, we will duplicate/drop to match CFR

        # We'll read source frames sequentially
        rendered_frames = 0
        history = []  # list of (x_export, y_export, provenance, visibility)

        # For audio handling, we will later mux if needed

        # Read all source frames into memory? No, streaming
        # For this implementation, we assume we render at source frame count but at export fps
        # For VFR to CFR conversion, we need to handle timestamp mapping: we will produce CFR output where each output frame corresponds to a time slice
        # Simplified: if manifest has pts, we will generate output frames at regular interval 1/export_fps and pick nearest source frame

        if pts_list and len(pts_list) > 1:
            # VFR handling: generate output frames based on duration
            duration_us = manifest.get("duration_us", pts_list[-1] + int(1e6/src_fps))
            num_output_frames = int((duration_us / 1e6) * export_fps)
            # For each output frame, find source frame with pts closest <= output pts
            for out_idx in range(num_output_frames):
                out_pts_us = int((out_idx / export_fps) * 1e6)
                # Find source frame index with pts <= out_pts_us (or nearest)
                # Use bisect
                import bisect
                src_idx = bisect.bisect_right(pts_list, out_pts_us) - 1
                if src_idx < 0:
                    src_idx = 0
                if src_idx >= frame_count:
                    src_idx = frame_count - 1

                # Seek to src_idx if needed (for simplicity, we read sequentially and assume out_idx corresponds to src_idx when fps similar)
                # For accurate VFR, we would need to seek. For performance, we will read sequentially and if src_idx != current, seek
                # Here we implement sequential with seeking when needed

                # For simplicity in this version, we will not seek per frame for performance; instead we read all frames into list of frames? But that would be memory heavy
                # We'll implement seeking
                cap.set(cv2.CAP_PROP_POS_FRAMES, src_idx)
                ret, frame = cap.read()
                if not ret:
                    # Try next
                    continue

                # Resize frame to export size with letterbox handling
                # Compute letterbox for canonical to export? Actually frame is encoded, but we assume canonical same as encoded for simplicity (rotation handled earlier)
                # Resize to export
                # For letterbox, we should compute scale and offsets
                # Here we simple resize with aspect preservation and letterbox black
                # Calculate scale
                scale = min(export_w / src_w, export_h / src_h)
                new_w = int(src_w * scale)
                new_h = int(src_h * scale)
                new_w = _ensure_even(new_w)
                new_h = _ensure_even(new_h)
                resized = cv2.resize(frame, (new_w, new_h))
                # Create black canvas
                canvas = np.zeros((export_h, export_w, 3), dtype=np.uint8)
                off_x = (export_w - new_w)//2
                off_y = (export_h - new_h)//2
                canvas[off_y:off_y+new_h, off_x:off_x+new_w] = resized

                # Now render tracer
                # Get track point for this source frame
                tp = track_map.get(src_idx)
                if tp and tp.x_norm is not None and tp.visibility == "visible":
                    # Map canonical to export: need canonical dimensions
                    # Assume canonical = src (after rotation)
                    canon_w, canon_h = src_w, src_h
                    # Map to export with letterbox
                    # Use canonical_to_export with canvas offset
                    # For simplicity, map normalized to export with same letterbox logic
                    # normalized -> canonical -> export
                    # canonical coords: x_norm * canon_w, y_norm * canon_h
                    canon_x = tp.x_norm * canon_w
                    canon_y = tp.y_norm * canon_h
                    # Map to export canvas coords
                    # Apply same letterbox as video
                    exp_x = canon_x * scale + off_x
                    exp_y = canon_y * scale + off_y
                    history.append((exp_x, exp_y, tp.provenance, tp.visibility))
                else:
                    # No visible point, keep history but don't add new
                    pass

                # Trim history to trail
                if len(history) > trail_frames:
                    history = history[-trail_frames:]

                # Draw trail
                if len(history) >= 2:
                    for i in range(1, len(history)):
                        x0,y0,prov0,_ = history[i-1]
                        x1,y1,prov1,_ = history[i]
                        # Determine opacity based on fade and age
                        age_factor = i / len(history) if fade else 1.0
                        alpha = opacity * age_factor
                        # Color
                        # For inferred segments, use different style
                        is_inferred = prov1 in ("interpolated","predicted","artistic") or prov0 in ("interpolated","predicted","artistic")
                        if is_inferred and inferred_style == "dashed":
                            # Dashed: draw only every other segment
                            if i % 2 == 0:
                                continue
                        # For glow, draw thicker blurred line underneath
                        if glow and glow_radius > 0:
                            cv2.line(canvas, (int(x0), int(y0)), (int(x1), int(y1)), color_bgr, stroke_px + glow_radius*2)
                        cv2.line(canvas, (int(x0), int(y0)), (int(x1), int(y1)), color_bgr, stroke_px)

                # Head marker
                if history:
                    hx, hy, _, _ = history[-1]
                    if head_marker == "circle":
                        cv2.circle(canvas, (int(hx), int(hy)), stroke_px*2, color_bgr, -1)
                        cv2.circle(canvas, (int(hx), int(hy)), stroke_px*2, (255,255,255), 1)
                    elif head_marker == "dot":
                        cv2.circle(canvas, (int(hx), int(hy)), stroke_px, color_bgr, -1)

                # Watermark
                watermark = self.style.get("watermark")
                if watermark:
                    text = watermark if isinstance(watermark, str) else "GolfTrace"
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    font_scale = 0.5
                    thickness = 1
                    # Bottom right
                    (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)
                    x = export_w - tw - 10
                    y = export_h - 10
                    cv2.putText(canvas, text, (x,y), font, font_scale, (255,255,255), thickness, cv2.LINE_AA)
                    cv2.putText(canvas, text, (x,y), font, font_scale, (0,0,0), thickness+1, cv2.LINE_AA)

                out.write(canvas)
                rendered_frames += 1
        else:
            # Constant FPS path
            frame_idx = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                scale = min(export_w / src_w, export_h / src_h)
                new_w = int(src_w * scale)
                new_h = int(src_h * scale)
                new_w = _ensure_even(new_w)
                new_h = _ensure_even(new_h)
                resized = cv2.resize(frame, (new_w, new_h))
                canvas = np.zeros((export_h, export_w, 3), dtype=np.uint8)
                off_x = (export_w - new_w)//2
                off_y = (export_h - new_h)//2
                canvas[off_y:off_y+new_h, off_x:off_x+new_w] = resized

                tp = track_map.get(frame_idx)
                if tp and tp.x_norm is not None and tp.visibility == "visible":
                    canon_x = tp.x_norm * src_w
                    canon_y = tp.y_norm * src_h
                    exp_x = canon_x * scale + off_x
                    exp_y = canon_y * scale + off_y
                    history.append((exp_x, exp_y, tp.provenance, tp.visibility))

                if len(history) > trail_frames:
                    history = history[-trail_frames:]

                if len(history) >= 2:
                    for i in range(1, len(history)):
                        x0,y0,prov0,_ = history[i-1]
                        x1,y1,prov1,_ = history[i]
                        age_factor = i / len(history) if fade else 1.0
                        is_inferred = prov1 in ("interpolated","predicted","artistic") or prov0 in ("interpolated","predicted","artistic")
                        if is_inferred and inferred_style == "dashed":
                            if i % 2 == 0:
                                continue
                        if glow and glow_radius>0:
                            cv2.line(canvas, (int(x0), int(y0)), (int(x1), int(y1)), color_bgr, stroke_px + glow_radius*2)
                        cv2.line(canvas, (int(x0), int(y0)), (int(x1), int(y1)), color_bgr, stroke_px)

                if history:
                    hx, hy, _, _ = history[-1]
                    if head_marker == "circle":
                        cv2.circle(canvas, (int(hx), int(hy)), stroke_px*2, color_bgr, -1)
                        cv2.circle(canvas, (int(hx), int(hy)), stroke_px*2, (255,255,255), 1)
                    elif head_marker == "dot":
                        cv2.circle(canvas, (int(hx), int(hy)), stroke_px, color_bgr, -1)

                # Watermark
                watermark = self.style.get("watermark")
                if watermark:
                    text = watermark if isinstance(watermark, str) else "GolfTrace"
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    font_scale = 0.5
                    thickness = 1
                    (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)
                    x = export_w - tw - 10
                    y = export_h - 10
                    cv2.putText(canvas, text, (x,y), font, font_scale, (255,255,255), thickness, cv2.LINE_AA)

                out.write(canvas)
                rendered_frames += 1
                frame_idx += 1

        cap.release()
        out.release()

        # Now handle audio and final transcoding to H264 yuv420p faststart
        # Try ffmpeg for final mux
        try:
            # Check if audio preserve and input has audio
            # Use ffprobe to check? For simplicity, try to copy audio if exists and preserve
            # We'll attempt ffmpeg command to mux audio from original and video from temp

            # First, check if input has audio via OpenCV? OpenCV doesn't give audio, so we try ffprobe if available
            has_audio = False
            try:
                cmd_probe = ["ffprobe", "-v", "quiet", "-show_streams", "-print_format", "json", input_video_path]
                res = subprocess.run(cmd_probe, capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    data = json.loads(res.stdout)
                    for s in data.get("streams", []):
                        if s.get("codec_type") == "audio":
                            has_audio = True
                            break
            except:
                pass

            if has_audio and audio_preserve:
                # Mux audio
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", temp_video_path,
                    "-i", input_video_path,
                    "-c:v", "libx264",
                    "-profile:v", "high",
                    "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart",
                    "-c:a", "aac",
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-shortest",
                    output_path
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=120)
                if result.returncode == 0 and os.path.exists(output_path):
                    os.remove(temp_video_path)
                    return
                # If failed, fallback to video only transcode

            # Video only transcode
            cmd = [
                "ffmpeg",
                "-y",
                "-i", temp_video_path,
                "-c:v", "libx264",
                "-profile:v", "high",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                output_path
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=120)
            if result.returncode == 0 and os.path.exists(output_path):
                os.remove(temp_video_path)
                return
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            pass

        # If ffmpeg not available or failed, just rename temp to output (may be mp4v not yuv420p but playable)
        if os.path.exists(temp_video_path):
            if os.path.exists(output_path):
                os.remove(output_path)
            os.rename(temp_video_path, output_path)
