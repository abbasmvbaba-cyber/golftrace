"""
Centralized geometry utilities for GolfTrace coordinate contract.

Spaces:
- encoded source pixels: raw decoded
- canonical display pixels: after rotation correction
- normalized [0,1] relative to canonical
- resized analysis pixels
- model crop/letterbox
- editor canvas pixels
- export pixels
- stabilized reference (via S_t transforms)

All functions tested for round-trip.
"""
import math
from typing import Tuple, Optional
import numpy as np

def _rotate_point(x: float, y: float, w: int, h: int, rotation: int) -> Tuple[float, float, int, int]:
    """
    Rotate point clockwise.
    rotation in [0,90,180,270]
    Returns (x', y', new_w, new_h)
    """
    rotation = rotation % 360
    if rotation == 0:
        return x, y, w, h
    elif rotation == 90:
        # 90 cw: (x,y) -> (y, w-1 - x) ??? But using continuous coordinates, not pixel indices.
        # For normalized continuous, we use w,h as extents.
        # After 90 cw, width becomes h, height becomes w.
        # Mapping: new_x = y, new_y = w - x
        return y, w - x, h, w
    elif rotation == 180:
        return w - x, h - y, w, h
    elif rotation == 270:
        # 270 cw = 90 ccw: (x,y) -> (h - y, x)
        return h - y, x, h, w
    else:
        raise ValueError(f"Unsupported rotation {rotation}")

def encoded_to_canonical(pt: Tuple[float,float], rotation: int, src_w: int, src_h: int) -> Tuple[float,float,Tuple[int,int]]:
    """pt in encoded pixels, returns (canonical_x, canonical_y, (canon_w, canon_h))"""
    x,y = pt
    cx, cy, cw, ch = _rotate_point(x, y, src_w, src_h, rotation)
    return (cx, cy), (cw, ch)

def canonical_to_encoded(pt: Tuple[float,float], rotation: int, src_w: int, src_h: int) -> Tuple[float,float]:
    """Inverse of encoded_to_canonical. src_w, src_h are original encoded dimensions."""
    x,y = pt
    # We need inverse rotation
    # Determine canonical dimensions
    if rotation in (90,270):
        canon_w, canon_h = src_h, src_w
    else:
        canon_w, canon_h = src_w, src_h

    if rotation == 0:
        return x, y
    elif rotation == 90:
        # forward: (x_enc, y_enc) -> (y_enc, w - x_enc)
        # inverse: x_enc = w - y_can, y_enc = x_can
        return src_w - y, x
    elif rotation == 180:
        return src_w - x, src_h - y
    elif rotation == 270:
        # forward: (x_enc, y_enc) -> (h - y_enc, x_enc)
        # inverse: x_enc = y_can, y_enc = h - x_can
        return y, src_h - x
    else:
        raise ValueError

def canonical_to_normalized(pt: Tuple[float,float], canon_w: int, canon_h: int) -> Tuple[float,float]:
    x,y = pt
    if canon_w == 0 or canon_h == 0:
        raise ValueError("zero dimension")
    return x / canon_w, y / canon_h

def normalized_to_canonical(npt: Tuple[float,float], canon_w: int, canon_h: int) -> Tuple[float,float]:
    nx, ny = npt
    return nx * canon_w, ny * canon_h

def canonical_to_analysis(pt: Tuple[float,float], canon_w: int, canon_h: int, analysis_w: int, analysis_h: int, keep_aspect=True) -> Tuple[float,float, dict]:
    """
    Map canonical to analysis resized. If keep_aspect, letterbox.
    Returns (ax, ay, meta) where meta contains scale, offset_x, offset_y, letterboxed bool.
    """
    if not keep_aspect:
        sx = analysis_w / canon_w
        sy = analysis_h / canon_h
        return pt[0]*sx, pt[1]*sy, {"scale_x": sx, "scale_y": sy, "offset_x":0, "offset_y":0, "letterboxed": False}
    else:
        scale = min(analysis_w / canon_w, analysis_h / canon_h)
        displayed_w = canon_w * scale
        displayed_h = canon_h * scale
        offset_x = (analysis_w - displayed_w) / 2
        offset_y = (analysis_h - displayed_h) / 2
        ax = pt[0]*scale + offset_x
        ay = pt[1]*scale + offset_y
        return ax, ay, {"scale": scale, "offset_x": offset_x, "offset_y": offset_y, "displayed_w": displayed_w, "displayed_h": displayed_h, "letterboxed": True}

def analysis_to_canonical(pt: Tuple[float,float], canon_w: int, canon_h: int, analysis_w: int, analysis_h: int, keep_aspect=True, meta: Optional[dict]=None) -> Tuple[float,float]:
    x,y = pt
    if not keep_aspect:
        sx = analysis_w / canon_w
        sy = analysis_h / canon_h
        return x / sx, y / sy
    else:
        if meta is None:
            scale = min(analysis_w / canon_w, analysis_h / canon_h)
            displayed_w = canon_w * scale
            displayed_h = canon_h * scale
            offset_x = (analysis_w - displayed_w) / 2
            offset_y = (analysis_h - displayed_h) / 2
        else:
            scale = meta["scale"]
            offset_x = meta["offset_x"]
            offset_y = meta["offset_y"]
        return (x - offset_x)/scale, (y - offset_y)/scale

def canvas_to_canonical(canvas_pt: Tuple[float,float], canvas_w: float, canvas_h: float, video_canon_w: int, video_canon_h: int, dpr: float=1.0) -> Tuple[float,float]:
    """
    Map canvas click (CSS pixels) to canonical video pixels, accounting for object-fit: contain.
    canvas_w,h are CSS size of canvas element.
    canvas_pt in CSS pixels relative to canvas top-left.
    """
    # Compute object-fit contain
    scale = min(canvas_w / video_canon_w, canvas_h / video_canon_h)
    displayed_w = video_canon_w * scale
    displayed_h = video_canon_h * scale
    offset_x = (canvas_w - displayed_w)/2
    offset_y = (canvas_h - displayed_h)/2

    # Adjust for DPR if canvas backing store uses DPR
    # Assume canvas_pt already in CSS pixels, not device pixels.
    # Convert to video space
    vx = (canvas_pt[0] - offset_x) / scale
    vy = (canvas_pt[1] - offset_y) / scale

    # Clamp to [0, canon]
    # We return unclamped but caller may clamp and check if inside video rect
    return vx, vy

def canonical_to_canvas(canon_pt: Tuple[float,float], canvas_w: float, canvas_h: float, video_canon_w: int, video_canon_h: int) -> Tuple[float,float]:
    scale = min(canvas_w / video_canon_w, canvas_h / video_canon_h)
    displayed_w = video_canon_w * scale
    displayed_h = video_canon_h * scale
    offset_x = (canvas_w - displayed_w)/2
    offset_y = (canvas_h - displayed_h)/2
    return canon_pt[0]*scale + offset_x, canon_pt[1]*scale + offset_y

def canonical_to_export(canon_pt: Tuple[float,float], canon_w: int, canon_h: int, export_w: int, export_h: int) -> Tuple[float,float]:
    # Similar to analysis but for export, keep aspect contain, but export typically same aspect? Use contain.
    scale = min(export_w / canon_w, export_h / canon_h)
    displayed_w = canon_w * scale
    displayed_h = canon_h * scale
    offset_x = (export_w - displayed_w)/2
    offset_y = (export_h - displayed_h)/2
    return canon_pt[0]*scale + offset_x, canon_pt[1]*scale + offset_y

def transform_point(pt: Tuple[float,float], matrix: np.ndarray) -> Tuple[float,float]:
    """Apply 3x3 homogeneous transform."""
    x,y = pt
    vec = np.array([x, y, 1.0])
    res = matrix @ vec
    if abs(res[2]) < 1e-9:
        return float(res[0]), float(res[1])
    return float(res[0]/res[2]), float(res[1]/res[2])

def compose_transforms(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Compose: A * B"""
    return A @ B

def invert_transform(M: np.ndarray) -> np.ndarray:
    return np.linalg.inv(M)

def compute_affine_transform(src_pts: np.ndarray, dst_pts: np.ndarray) -> np.ndarray:
    """
    Compute affine from src to dst using least squares.
    src_pts, dst_pts: Nx2
    Returns 3x3 matrix.
    """
    # Use OpenCV-like estimation? Use numpy.
    # Solve for 2x3 affine: [a,b,tx; c,d,ty]
    # For each point: x' = a*x + b*y + tx, y' = c*x + d*y + ty
    # Build linear system
    n = src_pts.shape[0]
    if n < 3:
        raise ValueError("need at least 3 points for affine")
    A = np.zeros((2*n, 6))
    b = np.zeros((2*n,))
    for i in range(n):
        x,y = src_pts[i]
        xp, yp = dst_pts[i]
        A[2*i, 0] = x
        A[2*i, 1] = y
        A[2*i, 2] = 1
        A[2*i+1, 3] = x
        A[2*i+1, 4] = y
        A[2*i+1, 5] = 1
        b[2*i] = xp
        b[2*i+1] = yp
    params, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
    M = np.array([
        [params[0], params[1], params[2]],
        [params[3], params[4], params[5]],
        [0,0,1]
    ])
    return M

def is_transform_plausible(M: np.ndarray, frame_w: int, frame_h: int) -> bool:
    """Reject implausible transforms: scale outside [0.8,1.25], translation >50% frame, rotation >10 deg per frame."""
    # Extract scale and rotation approx
    # For affine, top-left 2x2 contains rotation+scale
    a,b = M[0,0], M[0,1]
    c,d = M[1,0], M[1,1]
    # Scale: sqrt(a^2 + c^2) and sqrt(b^2 + d^2) approx
    scale_x = math.sqrt(a*a + c*c)
    scale_y = math.sqrt(b*b + d*d)
    if not (0.8 <= scale_x <= 1.25 and 0.8 <= scale_y <= 1.25):
        return False
    # Translation
    tx, ty = M[0,2], M[1,2]
    if abs(tx) > frame_w * 0.5 or abs(ty) > frame_h * 0.5:
        return False
    # Rotation: angle = atan2(c, a)
    rot_rad = math.atan2(c, a)
    rot_deg = abs(math.degrees(rot_rad))
    if rot_deg > 10:
        return False
    return True
