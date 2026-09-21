"""
Time contract implementation.
"""
from typing import List, Dict, Optional, Tuple
import bisect

class FrameEntry:
    def __init__(self, frame_index: int, pts_us: int, original_pts: Optional[int]=None, time_base: Optional[str]=None, keyframe: bool=False, width: int=0, height: int=0):
        self.frame_index = frame_index
        self.pts_us = pts_us
        self.original_pts = original_pts
        self.time_base = time_base
        self.keyframe = keyframe
        self.width = width
        self.height = height

    def to_dict(self):
        return {
            "frame_index": self.frame_index,
            "pts_us": self.pts_us,
            "original_pts": self.original_pts,
            "time_base": self.time_base,
            "keyframe": self.keyframe,
            "width": self.width,
            "height": self.height
        }

def normalize_pts(pts_list: List[int], time_base_num: float = 1e6) -> List[int]:
    """Convert original PTS to microseconds and normalize origin to 0."""
    if not pts_list:
        return []
    # pts in time_base units, convert to us
    # Assuming pts_list already in us? For generic, we assume conversion already done
    # Normalize
    first = pts_list[0]
    return [p - first for p in pts_list]

def validate_timestamps(frames: List[FrameEntry]) -> Tuple[bool, str, bool]:
    """
    Returns (is_valid, error_message, needs_repair)
    Policy: if missing PTS for <1% frames and monotonic can be inferred, repair.
    If >1% missing, duplicate, non-monotonic, reject.
    """
    if not frames:
        return False, "empty manifest", False

    missing = sum(1 for f in frames if f.pts_us is None)
    total = len(frames)
    if missing > 0:
        if missing / total < 0.01:
            # repairable
            return True, "", True
        else:
            return False, f"missing PTS for {missing}/{total} frames", False

    # Check duplicate and monotonic (presentation order should be increasing)
    pts_values = [f.pts_us for f in frames]
    # Allow equal? Duplicate PTS is invalid
    seen = set()
    for pts in pts_values:
        if pts in seen:
            # duplicate
            dup_ratio = pts_values.count(pts) / total
            if dup_ratio > 0.01:
                return False, f"duplicate PTS {pts}", False
        seen.add(pts)

    # Check monotonic increasing (allow small jitter? Must be increasing)
    for i in range(1, len(pts_values)):
        if pts_values[i] <= pts_values[i-1]:
            # Non-monotonic
            # Could be B-frame reordering already handled? Presentation order should be monotonic.
            # If violation, check ratio
            violations = sum(1 for j in range(1,len(pts_values)) if pts_values[j] <= pts_values[j-1])
            if violations / total > 0.01:
                return False, f"non-monotonic PTS at {i}", False
            else:
                return True, "", True

    return True, "", False

def repair_timestamps(frames: List[FrameEntry], fps_avg: Optional[float]=None) -> List[FrameEntry]:
    """Repair missing timestamps using fps_avg or neighboring."""
    if not frames:
        return frames
    # Find first valid
    # Simple: interpolate
    # If fps_avg given, use delta = 1e6/fps
    if fps_avg and fps_avg > 0:
        delta_us = int(1e6 / fps_avg)
    else:
        # Estimate from valid neighbors
        valid = [f for f in frames if f.pts_us is not None]
        if len(valid) >= 2:
            # average delta
            deltas = [valid[i].pts_us - valid[i-1].pts_us for i in range(1,len(valid))]
            avg_delta = sum(deltas)//len(deltas) if deltas else 33333
            delta_us = avg_delta
        else:
            delta_us = 33333  # 30fps

    last_pts = None
    for f in frames:
        if f.pts_us is None:
            if last_pts is None:
                f.pts_us = 0
            else:
                f.pts_us = last_pts + delta_us
        last_pts = f.pts_us

    # Ensure monotonic
    for i in range(1,len(frames)):
        if frames[i].pts_us <= frames[i-1].pts_us:
            frames[i].pts_us = frames[i-1].pts_us + delta_us

    # Normalize origin
    first = frames[0].pts_us
    for f in frames:
        f.pts_us -= first

    return frames

def map_preview_time_to_source_frame(preview_time_us: int, preview_manifest: List[FrameEntry], source_manifest: List[FrameEntry]) -> int:
    """
    Map preview time to source frame_index via nearest pts_us.
    If preview uses different fps, preview_time_us corresponds to preview frame's pts.
    Find source frame with nearest pts_us.
    """
    # Assume both manifests have pts_us normalized
    # Find index in source where pts_us closest to preview_time_us
    pts_list = [f.pts_us for f in source_manifest]
    idx = bisect.bisect_left(pts_list, preview_time_us)
    if idx >= len(pts_list):
        idx = len(pts_list)-1
    elif idx > 0:
        # Choose closer
        if abs(pts_list[idx] - preview_time_us) > abs(pts_list[idx-1] - preview_time_us):
            idx = idx-1
    return idx

def compute_dt_us(curr_pts_us: int, prev_pts_us: int) -> float:
    return (curr_pts_us - prev_pts_us) / 1e6
