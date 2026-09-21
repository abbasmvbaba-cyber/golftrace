# Coordinates and Time Contract

## Time Contract

### Definitions
- **Source PTS**: Presentation timestamp from container in stream time_base units. Retained as original_pts and time_base metadata where available.
- **pts_us**: Integer microseconds from normalized media time origin (first frame PTS = 0). Stored per frame in presentation order.
- **frame_index**: Integer presentation-order index (0..N-1). Canonical identifier for exact annotation.
- **Normalized origin**: 0 at first frame's PTS. All pts_us relative to this.

### VFR, B-frames
- Use presentation order, not decode order.
- Store pts_us from actual container PTS, not constant FPS assumption.
- Browser playback time is NOT exact-frame guarantee.
- For exact annotation, retrieve canonical frame by frame_index.
- If preview media uses different frame rate, map preview time -> source frame timestamps via manifest lookup (nearest pts_us).

### Delta Time
- Motion models must use actual delta time: `dt = (pts_us[t] - pts_us[t-1]) / 1e6`
- Variable FPS supported up to 120 FPS.

### Missing/Duplicate/Invalid Timestamps
Policy:
- If PTS missing for <1% frames and monotonic can be inferred from FPS, repair with recorded metadata `pts_repaired=true` and log warning.
- If >1% missing, duplicate, or non-monotonic (excluding B-frame reordering already handled by presentation order), reject with explicit error code `INVALID_TIMESTAMPS`.
- Never silently invent timing.

### Frame Manifest
JSON stored in object storage, schema version 1:
```json
{
  "schema_version": 1,
  "video_id": "...",
  "duration_us": 12345678,
  "frame_count": 1800,
  "frames": [
    {"frame_index": 0, "pts_us": 0, "original_pts": 0, "time_base": "1/30000", "keyframe": true, "width": 1920, "height": 1080},
    ...
  ],
  "time_repaired": false,
  "vfr": true
}
```

## Coordinate Contract

### Canonical System
- Canonical annotation coordinate system = orientation-corrected display frame.
- Orientation correction from rotation metadata (90,180,270) and flip.
- Store normalized coordinates [0,1] relative to canonical width/height.
- `null` means unavailable, never 0.

### Transforms
All transforms centralized and tested.

**Spaces:**
1. **encoded source pixels**: raw decoded frame pixels before rotation
2. **canonical display pixels**: after rotation correction, this is what user sees as "original"
3. **resized analysis pixels**: downscaled for tracking (e.g., long edge 1280)
4. **model crop/letterbox**: model input with letterboxing
5. **stabilized reference**: after applying S_t inverse? Actually S_t maps canonical t -> reference. For storage, points stored in canonical.
6. **editor canvas pixels**: canvas element pixels with object-fit, DPR, letterbox offsets
7. **export pixels**: final render resolution (up to 1080p)

**Functions (backend/app/core/geometry.py, frontend/src/utils/geometry.ts):**
- `encoded_to_canonical(pt, rotation, src_w, src_h) -> canonical`
- `canonical_to_encoded(pt, rotation, ...)`
- `canonical_to_normalized(pt, canonical_w, canonical_h) -> (nx, ny)`
- `normalized_to_canonical(npt, canonical_w, canonical_h)`
- `canonical_to_analysis(pt, canonical_w, canonical_h, analysis_w, analysis_h) // letterbox aware?`
- `analysis_to_canonical(...)`
- `model_letterbox_to_analysis(...)`
- `canvas_to_canonical(canvas_pt, canvas_rect, video_rect, dpr, letterbox_offsets)`
- `canonical_to_canvas(...)`
- `canonical_to_export(...)`
- `transform_point(pt, matrix_3x3)`

**Letterboxing:**
- When fitting video into canvas with `object-fit: contain`, compute offsets:
  ```
  scale = min(canvas_w / video_w, canvas_h / video_h)
  displayed_w = video_w * scale
  displayed_h = video_h * scale
  offset_x = (canvas_w - displayed_w)/2
  offset_y = (canvas_h - displayed_h)/2
  ```
- Click mapping must subtract offset and divide by scale.

**Rotation:**
- Handle 0,90,180,270. Swap width/height for 90/270.
- Transform:
  - 0: (x,y)
  - 90: (y, src_h - x) ??? Actually depending on convention. Document: rotation is clockwise. So 90 cw: (x,y) in encoded (w,h) -> canonical (h,w) with (y, w - x)?? Test round-trip.

**Camera Motion:**
- `S_t`: 3x3 affine from canonical frame t to its segment reference.
- For historical point from frame i rendered in frame t:
  `p_current = inverse(S_t) * S_i * p_i`
- Composition: `S_i` already maps frame i to reference. So `S_i * p_i` gives point in reference. Then `inverse(S_t)` maps reference back to current frame t.

**Testing:**
- Round-trip tests for all pairs.
- Rotation 90/180/270 round-trip.
- Letterbox click mapping round-trip.
- Canvas mapping with DPR.

### Style Contract
- Tracer color: hex
- Stroke width: normalized (relative to export height, e.g., 0.005 = 0.5% of height)
- Glow: boolean + radius normalized
- Opacity: 0..1
- Trail duration: ms
- Fade: boolean
- Head marker: enum none/circle/dot
- Progressive reveal: boolean
- Inferred segment style: distinct (dashed, opacity 0.6)
- Watermark optional
- Audio preservation preference

All validated and bounded.

One documented style + path-sampling contract for browser preview and server export must match.

