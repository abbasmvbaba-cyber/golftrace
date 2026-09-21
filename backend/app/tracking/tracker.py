"""
Temporal tracker with Kalman, gating, multi-hypothesis, anchor constraints.
"""
import math
from typing import List, Dict, Optional
import numpy as np
from .interfaces import FrameData, Candidate, TrackPoint, CameraMotion
from .kalman import KalmanFilter2D

class Hypothesis:
    def __init__(self, kf: KalmanFilter2D, track: List[TrackPoint], score: float, misses: int = 0):
        self.kf = kf
        self.track = track
        self.score = score
        self.misses = misses

class TemporalTracker:
    def __init__(self, beam_width: int = 3, gating_threshold: float = 9.21, max_misses_before_expansion: int = 5, max_search_radius_factor: float = 3.0):
        # gating_threshold 9.21 corresponds to 99% for chi2 2dof
        self.beam_width = beam_width
        self.gating_threshold = gating_threshold
        self.max_misses_before_expansion = max_misses_before_expansion
        self.max_search_radius_factor = max_search_radius_factor

    def track(self, frames: List[FrameData], candidates: Dict[int, List[Candidate]], anchors: Dict[int, TrackPoint], camera_motion: CameraMotion, config: Dict) -> List[TrackPoint]:
        if not frames:
            return []

        # Sort frames by frame_index
        frames_sorted = sorted(frames, key=lambda f: f.frame_index)
        # Build anchor map
        anchor_map = anchors  # frame_index -> TrackPoint

        # Initialize hypotheses
        hypotheses: List[Hypothesis] = []

        # If first frame has anchor, init from there
        first_frame = frames_sorted[0]
        first_idx = first_frame.frame_index
        if first_idx in anchor_map and anchor_map[first_idx].visibility == "visible" and anchor_map[first_idx].x_norm is not None:
            anc = anchor_map[first_idx]
            kf = KalmanFilter2D()
            kf.init(anc.x_norm, anc.y_norm)
            tp = TrackPoint(frame_index=first_idx, pts_us=first_frame.pts_us, x_norm=anc.x_norm, y_norm=anc.y_norm,
                            provenance="manual", visibility="visible", score=1.0, is_anchor=True)
            hypotheses.append(Hypothesis(kf=kf, track=[tp], score=0, misses=0))
        else:
            # Try candidates at first frame
            cands = candidates.get(first_idx, [])
            if cands:
                for cand in cands[:self.beam_width]:
                    kf = KalmanFilter2D()
                    kf.init(cand.x_norm, cand.y_norm)
                    tp = TrackPoint(frame_index=first_idx, pts_us=first_frame.pts_us, x_norm=cand.x_norm, y_norm=cand.y_norm,
                                    provenance="detected", visibility="visible", score=cand.score)
                    hypotheses.append(Hypothesis(kf=kf, track=[tp], score=1-cand.score))
            else:
                # Start with missing
                kf = KalmanFilter2D()
                tp = TrackPoint(frame_index=first_idx, pts_us=first_frame.pts_us, x_norm=None, y_norm=None,
                                provenance="predicted", visibility="not_visible", score=None)
                hypotheses.append(Hypothesis(kf=kf, track=[tp], score=10, misses=1))

        # Iterate frames
        prev_pts_us = first_frame.pts_us
        for frame in frames_sorted[1:]:
            curr_idx = frame.frame_index
            curr_pts_us = frame.pts_us
            dt = (curr_pts_us - prev_pts_us) / 1e6
            if dt <= 0:
                dt = 1/30.0

            new_hypotheses: List[Hypothesis] = []

            # Check anchor at this frame
            has_anchor = curr_idx in anchor_map
            anchor_pt = anchor_map.get(curr_idx)

            if has_anchor and anchor_pt:
                if anchor_pt.visibility != "visible" or anchor_pt.x_norm is None:
                    # Force missing / not visible
                    for hyp in hypotheses:
                        hyp.kf.predict(dt)
                        hyp.kf.inflate_covariance(1.2)
                        tp = TrackPoint(frame_index=curr_idx, pts_us=curr_pts_us, x_norm=None, y_norm=None,
                                        provenance="manual", visibility=anchor_pt.visibility, score=None, is_anchor=True)
                        new_track = hyp.track + [tp]
                        new_hypotheses.append(Hypothesis(kf=hyp.kf, track=new_track, score=hyp.score, misses=hyp.misses+1))
                    # Prune and continue
                    hypotheses = sorted(new_hypotheses, key=lambda h: h.score)[:self.beam_width]
                    prev_pts_us = curr_pts_us
                    continue
                else:
                    # Force anchor
                    for hyp in hypotheses:
                        hyp.kf.predict(dt)
                        # Update with anchor (high confidence)
                        hyp.kf.update(anchor_pt.x_norm, anchor_pt.y_norm, r_scale=0.1)
                        tp = TrackPoint(frame_index=curr_idx, pts_us=curr_pts_us, x_norm=anchor_pt.x_norm, y_norm=anchor_pt.y_norm,
                                        provenance="manual", visibility="visible", score=1.0, is_anchor=True)
                        new_track = hyp.track + [tp]
                        new_hypotheses.append(Hypothesis(kf=hyp.kf, track=new_track, score=hyp.score, misses=0))
                    hypotheses = sorted(new_hypotheses, key=lambda h: h.score)[:self.beam_width]
                    prev_pts_us = curr_pts_us
                    continue

            # No anchor, process candidates
            cands = candidates.get(curr_idx, [])

            for hyp in hypotheses:
                hyp.kf.predict(dt)

                # Gating
                gated_cands = []
                for cand in cands:
                    dist = hyp.kf.gating_distance(cand.x_norm, cand.y_norm)
                    if dist <= self.gating_threshold:
                        # Compute cost: motion compatibility (dist) + appearance (1-score) + scale etc
                        motion_cost = dist
                        appearance_cost = 1 - cand.score
                        total_cost = motion_cost * 0.5 + appearance_cost * 0.5
                        gated_cands.append((cand, total_cost, dist))

                gated_cands.sort(key=lambda x: x[1])

                if gated_cands:
                    # Expand hypothesis for each gated candidate up to beam_width
                    for cand, cost, dist in gated_cands[:self.beam_width]:
                        # Clone KF
                        kf_clone = KalmanFilter2D()
                        # Deep copy state
                        kf_clone.x = hyp.kf.x.copy()
                        kf_clone.P = hyp.kf.P.copy()
                        kf_clone.initialized = hyp.kf.initialized
                        kf_clone.q_vel = hyp.kf.q_vel
                        kf_clone.r_pos = hyp.kf.r_pos
                        # Update
                        r_scale = max(0.5, 1.5 - cand.score)  # higher score -> lower R
                        kf_clone.update(cand.x_norm, cand.y_norm, r_scale=r_scale)
                        tp = TrackPoint(frame_index=curr_idx, pts_us=curr_pts_us, x_norm=cand.x_norm, y_norm=cand.y_norm,
                                        provenance="detected", visibility="visible", score=cand.score)
                        new_track = hyp.track + [tp]
                        new_score = hyp.score + cost
                        new_hypotheses.append(Hypothesis(kf=kf_clone, track=new_track, score=new_score, misses=0))
                else:
                    # No candidate: missing observation
                    # Inflate covariance
                    hyp.kf.inflate_covariance(1.5)
                    # Predicted position
                    px, py = hyp.kf.get_pos() if hyp.kf.initialized else (None, None)
                    # If misses too many, we output missing (null)
                    if hyp.misses >= 2:
                        # After 2 misses, we output null but keep predicting internally
                        tp = TrackPoint(frame_index=curr_idx, pts_us=curr_pts_us, x_norm=None, y_norm=None,
                                        provenance="predicted", visibility="not_visible", score=None)
                    else:
                        # Keep predicted visible for short gaps
                        if px is not None:
                            tp = TrackPoint(frame_index=curr_idx, pts_us=curr_pts_us, x_norm=px, y_norm=py,
                                            provenance="predicted", visibility="visible", score=None)
                        else:
                            tp = TrackPoint(frame_index=curr_idx, pts_us=curr_pts_us, x_norm=None, y_norm=None,
                                            provenance="predicted", visibility="not_visible", score=None)
                    new_track = hyp.track + [tp]
                    # Increase misses
                    new_misses = hyp.misses + 1
                    # Add cost for miss
                    miss_cost = 2.0 + new_misses * 0.5
                    new_hypotheses.append(Hypothesis(kf=hyp.kf, track=new_track, score=hyp.score + miss_cost, misses=new_misses))

            # Prune to beam_width
            new_hypotheses.sort(key=lambda h: h.score)
            hypotheses = new_hypotheses[:self.beam_width]

            # Bounded reacquisition: if all hypotheses have many misses, increase search radius for next frame
            # This is handled via covariance inflation already

            prev_pts_us = curr_pts_us

            # Early exit if no hypotheses
            if not hypotheses:
                break

        # Choose best hypothesis
        if not hypotheses:
            return []

        best = min(hypotheses, key=lambda h: h.score)
        return best.track
