"""
Visual tolerance tests for render output, not binary MP4 equality.
"""
import sys
sys.path.insert(0, "/home/user/backend")
import tempfile, os, cv2, numpy as np, json
from app.tracking.renderer import VideoRenderer
from app.tracking.interfaces import TrackPoint
from tests.fixtures.synthetic import create_static_camera_fixture

def test_render_visual_tolerance():
    tmpdir = tempfile.mkdtemp()
    video_path = os.path.join(tmpdir, "static.mp4")
    create_static_camera_fixture(video_path, width=320, height=180, duration_sec=1, fps=10)

    # Create simple track: diagonal line
    track = []
    for i in range(10):
        track.append(TrackPoint(frame_index=i, pts_us=i*100000, x_norm=i/10, y_norm=i/10, provenance="manual", visibility="visible"))

    manifest = {"frames": [{"frame_index": i, "pts_us": i*100000} for i in range(10)], "duration_us": 1000000}

    out_path = os.path.join(tmpdir, "out.mp4")
    style = {
        "color": "#FF0000",
        "stroke_width_norm": 0.02,  # thicker for visual tolerance
        "glow": False,
        "opacity": 1.0,
        "trail_duration_ms": 5000,
        "fade": False,
        "head_marker": "circle",
        "progressive_reveal": True,
        "inferred_style": "solid",
        "audio_preserve": False,
        "watermark": "Test"
    }
    renderer = VideoRenderer(style=style, export_config={"width":320,"height":180,"fps":10})
    renderer.render(video_path, track, out_path, manifest)

    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 0

    # Verify tracer positions with visual tolerance
    cap = cv2.VideoCapture(out_path)
    assert cap.isOpened()
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    assert frame_count > 0

    # Read last frame, check if red tracer exists near expected position
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_count-1)
    ret, frame = cap.read()
    cap.release()
    assert ret

    # Expected position: last track point at 0.9,0.9 normalized -> 288,162 in 320x180
    # Check if red pixels exist in neighborhood
    # Red in BGR is (0,0,255)
    x_expected = int(0.9 * 320)
    y_expected = int(0.9 * 180)
    # Search 20px neighborhood
    found_red = False
    for dy in range(-20,21):
        for dx in range(-20,21):
            y = y_expected + dy
            x = x_expected + dx
            if 0 <= y < frame.shape[0] and 0 <= x < frame.shape[1]:
                b,g,r = frame[y,x]
                if r > 150 and g < 100 and b < 100:  # reddish
                    found_red = True
                    break
        if found_red:
            break

    assert found_red, "Red tracer not found near expected position, visual tolerance failed"
    print("test_render_visual_tolerance passed")

if __name__ == "__main__":
    test_render_visual_tolerance()
