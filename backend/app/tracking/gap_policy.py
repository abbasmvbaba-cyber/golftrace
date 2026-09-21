"""
Gap and display policy.
Default max auto interpolation gap 100ms, configurable.
Only interpolate inside valid continuous segments, not across scene cuts.
"""
from typing import List
from .interfaces import TrackPoint, CameraMotion

class GapPolicy:
    def __init__(self, max_gap_ms: int = 100):
        self.max_gap_ms = max_gap_ms

    def apply(self, track: List[TrackPoint], camera_motion: CameraMotion = None) -> List[TrackPoint]:
        """
        Apply gap policy: interpolate only inside valid continuous segments, up to max_gap_ms.
        Preserves raw observations separately? This function returns display path.
        For now, we interpolate missing where gap <= max_gap_ms and surrounded by visible points.
        """
        if not track:
            return []

        # Sort by frame_index
        track_sorted = sorted(track, key=lambda p: p.frame_index)

        # Build segments based on camera_motion segments if provided
        # For simplicity, assume no scene cut unless camera_motion indicates
        # We'll create list of segments (continuous)
        # For gap interpolation, only inside same camera segment

        # Map frame_index to segment id
        segment_map = {}
        if camera_motion and camera_motion.segments:
            for seg_id, (start, end) in enumerate(camera_motion.segments):
                for fi in range(start, end+1):
                    segment_map[fi] = seg_id
        else:
            # Single segment
            for tp in track_sorted:
                segment_map[tp.frame_index] = 0

        result = []
        i = 0
        while i < len(track_sorted):
            curr = track_sorted[i]
            result.append(curr)

            # Look ahead for gap
            if curr.x_norm is None or curr.visibility != "visible":
                # Already missing, just continue
                i += 1
                continue

            # Find next visible point
            j = i+1
            while j < len(track_sorted) and (track_sorted[j].x_norm is None or track_sorted[j].visibility != "visible"):
                j += 1

            if j >= len(track_sorted):
                # No next visible
                i += 1
                continue

            next_visible = track_sorted[j]
            gap_frames = j - i - 1
            if gap_frames == 0:
                i += 1
                continue

            # Check if same camera segment
            curr_seg = segment_map.get(curr.frame_index, 0)
            next_seg = segment_map.get(next_visible.frame_index, 0)
            if curr_seg != next_seg:
                # Do not interpolate across scene cuts
                # Fill gap with missing
                for k in range(i+1, j):
                    missing = track_sorted[k]
                    # Ensure it's missing
                    result.append(missing)
                i = j
                continue

            # Check gap duration
            gap_us = next_visible.pts_us - curr.pts_us
            gap_ms = gap_us / 1000.0

            if gap_ms <= self.max_gap_ms:
                # Interpolate
                for k in range(i+1, j):
                    tp = track_sorted[k]
                    # Linear interpolation in normalized coords
                    t = (tp.pts_us - curr.pts_us) / (next_visible.pts_us - curr.pts_us) if next_visible.pts_us != curr.pts_us else 0
                    x_interp = curr.x_norm + t * (next_visible.x_norm - curr.x_norm)
                    y_interp = curr.y_norm + t * (next_visible.y_norm - curr.y_norm)
                    interp_pt = TrackPoint(
                        frame_index=tp.frame_index,
                        pts_us=tp.pts_us,
                        x_norm=x_interp,
                        y_norm=y_interp,
                        provenance="interpolated",
                        visibility="visible",
                        score=None
                    )
                    result.append(interp_pt)
            else:
                # Gap too long, keep as missing / predicted but mark as needing review
                for k in range(i+1, j):
                    result.append(track_sorted[k])

            i = j
            continue

        # Sort result by frame_index and deduplicate
        result_sorted = sorted(result, key=lambda p: p.frame_index)
        # Remove duplicates (keep last)
        dedup = {}
        for p in result_sorted:
            dedup[p.frame_index] = p
        final = [dedup[k] for k in sorted(dedup.keys())]

        # Fill any missing frames that were not in original? We assume original track covers all frames in analysis interval
        return final

class DisplayPathGenerator:
    def __init__(self, max_gap_ms: int = 100, artistic_extension: bool = False):
        self.gap_policy = GapPolicy(max_gap_ms=max_gap_ms)
        self.artistic_extension = artistic_extension

    def generate(self, track: List[TrackPoint], camera_motion: CameraMotion = None, config: dict = None) -> List[TrackPoint]:
        # Apply gap policy
        display = self.gap_policy.apply(track, camera_motion)

        # Artistic extension disabled by default
        if not self.artistic_extension:
            return display

        # If enabled, extend beyond valid data with explicit artistic provenance
        # For now, just return display, extension requires explicit user action
        return display
