import sys
sys.path.insert(0, "/home/user/backend")
from app.core.time import FrameEntry, validate_timestamps, repair_timestamps, map_preview_time_to_source_frame, compute_dt_us

def test_validate_ok():
    frames = [FrameEntry(i, i*33333) for i in range(10)]
    valid, msg, repair = validate_timestamps(frames)
    assert valid and not repair

def test_validate_duplicate():
    frames = [FrameEntry(0,0), FrameEntry(1,0), FrameEntry(2,33333)]*5  # many duplicates
    # Actually need >1% duplicate
    frames = [FrameEntry(i, 0 if i<5 else i*33333) for i in range(100)]
    valid, msg, repair = validate_timestamps(frames)
    # 5 duplicates out of 100 = 5% >1% so invalid
    assert not valid

def test_repair():
    frames = [FrameEntry(0,0), FrameEntry(1,None), FrameEntry(2,66666)]
    repaired = repair_timestamps(frames, fps_avg=30)
    assert repaired[1].pts_us is not None
    assert repaired[0].pts_us == 0

def test_map_preview():
    src = [FrameEntry(i, i*33333) for i in range(100)]
    preview = [FrameEntry(i, i*33333) for i in range(100)]
    idx = map_preview_time_to_source_frame(50000, preview, src)
    # 50000 close to frame 1 (33333) or 2 (66666), should pick 2? Actually 50000 closer to 33333? diff 16667 vs 16666, so picks 2
    assert idx in (1,2)

def test_dt():
    dt = compute_dt_us(1000000, 0)
    assert abs(dt - 1.0) < 1e-6

if __name__ == "__main__":
    test_validate_ok()
    test_validate_duplicate()
    test_repair()
    test_map_preview()
    test_dt()
    print("All time tests passed")
