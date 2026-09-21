import sys
sys.path.insert(0, "/home/user/backend")
from app.tracking.kalman import KalmanFilter2D
from app.tracking.gap_policy import GapPolicy
from app.tracking.interfaces import TrackPoint
from app.core.time import compute_dt_us

def test_kalman_variable_dt():
    kf = KalmanFilter2D()
    kf.init(0.5,0.5)
    kf.predict(1/30)
    kf.update(0.51,0.51)
    x,y = kf.get_pos()
    assert abs(x-0.51) < 0.1
    # Variable dt
    kf.predict(1/60)
    kf.update(0.52,0.52)
    x2,y2 = kf.get_pos()
    assert x2>0.5

def test_gating():
    kf = KalmanFilter2D()
    kf.init(0.5,0.5)
    kf.predict(0.033)
    dist_close = kf.gating_distance(0.51,0.51)
    dist_far = kf.gating_distance(0.9,0.9)
    assert dist_close < dist_far

def test_missing_detection():
    # Tracker should return missing when no candidates
    from app.tracking.tracker import TemporalTracker
    from app.tracking.interfaces import FrameData
    import numpy as np
    frames = []
    for i in range(5):
        img = np.zeros((100,100,3), dtype=np.uint8)
        frames.append(FrameData(frame_index=i, pts_us=i*33333, image=img, canonical_width=100, canonical_height=100))
    candidates = {i: [] for i in range(5)}
    anchors = {}
    from app.tracking.interfaces import CameraMotion
    cam = CameraMotion(transforms=[np.eye(3)]*5, segments=[(0,4)], quality={})
    tracker = TemporalTracker()
    track = tracker.track(frames, candidates, anchors, cam, {})
    # Should have missing
    assert len(track) == 5
    # At least some missing
    missing = sum(1 for p in track if p.x_norm is None)
    assert missing >= 1

def test_gap_policy():
    pts = []
    for i in range(10):
        if i in (0,9):
            pts.append(TrackPoint(frame_index=i, pts_us=i*33333, x_norm=i/10, y_norm=0.5, provenance="manual", visibility="visible"))
        else:
            pts.append(TrackPoint(frame_index=i, pts_us=i*33333, x_norm=None, y_norm=None, provenance="predicted", visibility="not_visible"))
    policy = GapPolicy(max_gap_ms=100)
    # Gap from 0 to 9 is 300ms, exceeds 100ms, so should not interpolate
    result = policy.apply(pts)
    # Check middle still missing
    assert result[5].x_norm is None

    # Now small gap
    pts2 = []
    for i in range(5):
        if i in (0,2):
            pts2.append(TrackPoint(frame_index=i, pts_us=i*33333, x_norm=i/10, y_norm=0.5, provenance="manual", visibility="visible"))
        else:
            pts2.append(TrackPoint(frame_index=i, pts_us=i*33333, x_norm=None, y_norm=None, provenance="predicted", visibility="not_visible"))
    # Gap 0->2 = 66ms, should interpolate
    result2 = policy.apply(pts2)
    assert result2[1].x_norm is not None
    assert result2[1].provenance == "interpolated"

def test_manual_anchor_preservation():
    from app.tracking.gap_policy import GapPolicy
    pts = [
        TrackPoint(frame_index=0, pts_us=0, x_norm=0.1, y_norm=0.1, provenance="manual", visibility="visible", is_anchor=True),
        TrackPoint(frame_index=1, pts_us=33333, x_norm=None, y_norm=None, provenance="predicted", visibility="not_visible"),
        TrackPoint(frame_index=2, pts_us=66666, x_norm=0.3, y_norm=0.3, provenance="manual", visibility="visible", is_anchor=True),
    ]
    policy = GapPolicy(max_gap_ms=100)
    result = policy.apply(pts)
    # Anchors should be preserved
    assert result[0].x_norm == 0.1 and result[0].is_anchor
    assert result[2].x_norm == 0.3

if __name__ == "__main__":
    test_kalman_variable_dt()
    test_gating()
    test_missing_detection()
    test_gap_policy()
    test_manual_anchor_preservation()
    print("All tracking tests passed")
