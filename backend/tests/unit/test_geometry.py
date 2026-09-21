import sys
sys.path.insert(0, "/home/user/backend")
from app.core.geometry import (
    encoded_to_canonical, canonical_to_encoded,
    canonical_to_normalized, normalized_to_canonical,
    canonical_to_analysis, analysis_to_canonical,
    canvas_to_canonical, canonical_to_canvas,
    transform_point, compose_transforms, invert_transform,
    is_transform_plausible
)
import numpy as np

def test_rotation_roundtrip():
    w,h = 1920,1080
    points = [(100,100), (0,0), (1919,1079), (960,540)]
    for rot in [0,90,180,270]:
        for pt in points:
            canon, (cw,ch) = encoded_to_canonical(pt, rot, w, h)
            back = canonical_to_encoded(canon, rot, w, h)
            assert abs(back[0]-pt[0]) < 1e-5 and abs(back[1]-pt[1]) < 1e-5, f"rot {rot} pt {pt} -> {canon} -> {back}"

def test_normalized_roundtrip():
    canon_w, canon_h = 1920,1080
    pt = (960,540)
    npt = canonical_to_normalized(pt, canon_w, canon_h)
    back = normalized_to_canonical(npt, canon_w, canon_h)
    assert abs(back[0]-pt[0]) < 1e-5

def test_analysis_letterbox_roundtrip():
    canon_w, canon_h = 1920,1080
    analysis_w, analysis_h = 1280,720
    pt = (960,540)
    ax, ay, meta = canonical_to_analysis(pt, canon_w, canon_h, analysis_w, analysis_h, keep_aspect=True)
    back = analysis_to_canonical((ax,ay), canon_w, canon_h, analysis_w, analysis_h, keep_aspect=True, meta=meta)
    assert abs(back[0]-pt[0]) < 1e-3 and abs(back[1]-pt[1]) < 1e-3

def test_canvas_mapping_roundtrip():
    canvas_w, canvas_h = 800,600
    video_w, video_h = 1920,1080
    canon_pt = (960,540)
    canvas_pt = canonical_to_canvas(canon_pt, canvas_w, canvas_h, video_w, video_h)
    back = canvas_to_canonical(canvas_pt, canvas_w, canvas_h, video_w, video_h)
    assert abs(back[0]-canon_pt[0]) < 1e-2

def test_transform_composition():
    M1 = np.eye(3)
    M1[0,2] = 10
    M1[1,2] = 20
    M2 = np.eye(3)
    M2[0,0] = 2
    M2[1,1] = 2
    composed = compose_transforms(M1, M2)
    pt = (5,5)
    # Apply M2 then M1
    p2 = transform_point(pt, M2)
    p12 = transform_point(p2, M1)
    p_composed = transform_point(pt, composed)
    assert abs(p12[0]-p_composed[0]) < 1e-5

def test_plausible_transform():
    M = np.eye(3)
    assert is_transform_plausible(M, 1920,1080) == True
    M_bad_scale = np.eye(3)
    M_bad_scale[0,0] = 2.0
    assert is_transform_plausible(M_bad_scale, 1920,1080) == False
    M_bad_trans = np.eye(3)
    M_bad_trans[0,2] = 2000
    assert is_transform_plausible(M_bad_trans, 1920,1080) == False

if __name__ == "__main__":
    test_rotation_roundtrip()
    test_normalized_roundtrip()
    test_analysis_letterbox_roundtrip()
    test_canvas_mapping_roundtrip()
    test_transform_composition()
    test_plausible_transform()
    print("All geometry tests passed")
