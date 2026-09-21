# Tracking

## Interfaces

### FrameSource
```python
class FrameSource:
  def get_frame(frame_index) -> Frame
  def get_canonical_frame(frame_index) -> np.ndarray
  def manifest -> FrameManifest
```

### CandidateDetector
```python
class Candidate:
  x_norm, y_norm: float
  score: float
  radius: float
  provenance: "detected"
  frame_index: int

class CandidateDetector:
  def detect(frame, roi, camera_transform) -> List[Candidate]
```

### CameraMotionEstimator
```python
class CameraMotionEstimator:
  def estimate(frames) -> Tuple[List[Matrix3x3], List[Segment], quality_metrics]
```
- Prefer affine or partial-affine (translation+rotation+scale, no shear) initially.
- Robust fitting: RANSAC with threshold.
- Reject implausible transforms: scale outside [0.8,1.25], translation >50% frame per frame, rotation >10 deg per frame.
- Homography only when justified and validated (require planar check).
- Scene cut detection: if inlier ratio <0.3 and residual > threshold, create new segment.
- Output S_t per frame.

### TemporalTracker
```python
class TemporalTracker:
  def track(manifest, candidates_per_frame, anchors, camera_motion, config) -> Track
```
- Use user anchors as high-priority constraints.
- Image evidence: local contrast, motion cues, frame differences (after camera compensation), bounded local search.
- Template matching / optical flow auxiliary.
- Kalman-style with variable dt: state [x,y,vx,vy], F depends on dt, Q scales with dt.
- Uncertainty-aware gating: Mahalanobis distance.
- Costs: motion compatibility, appearance, scale, background consistency, detector score.
- Keep >1 hypothesis where ambiguity (beam width 3-5).
- Do not force selection when evidence insufficient -> missing observation.
- Increase search uncertainty after misses (covariance inflation).
- Bounded reacquisition: after miss, search radius *= 1.5 per frame up to max.
- Return missing observations when fails.
- Do not classify disappearance as out-of-frame with certainty based only on proximity to boundary.

### GapPolicy
- Default max auto interpolation gap 100ms, configurable.
- Only interpolate inside valid continuous segments.
- Do not connect across scene cuts.
- Long gaps require user review or manual anchors.
- Artistic extension disabled by default.

### DisplayPathGenerator
- Input: raw observations (detected/manual) + filtered estimates + track state
- Output: display path with segments labeled: detected, manual, predicted, interpolated, artistic (if enabled)
- Preserve raw observations separately from filtered estimates and display paths.
- Preserve manual anchors or disclose any adjustment.
- Do not label heuristic quality scores as calibrated probabilities.

### Renderer
- Maps output timestamps to source timestamps
- Supports VFR input while producing CFR export
- Respects gaps and provenance
- Does not extend beyond valid data
- Renders tracer, glow, fade, head marker

## Classical Detector Implementation (v1)

**Steps per frame:**
1. Compensate camera motion: warp previous frame to current using inverse S.
2. Compute absolute difference, threshold for moving small objects.
3. Compute local contrast: LoG or DoG filter, or white top-hat for bright ball on green.
4. Find contours, filter by area (ball radius 2-20px in analysis resolution), circularity, aspect.
5. Score candidates: contrast * motion * size prior * distance to predicted Kalman.
6. Return top-K.

**Kalman:**
- State: x,y,vx,vy
- F = [[1,0,dt,0],[0,1,0,dt],[0,0,1,0],[0,0,0,1]]
- H = [[1,0,0,0],[0,1,0,0]]
- Q = diag([0,0, q_vel, q_vel]) * dt, plus small pos noise
- R adaptive based on candidate score
- Gate: if innovation > 3 sigma, reject.

**Hypotheses:**
- Keep beam of 3 tracks.
- At each frame, expand each hypothesis with candidates within gate + miss hypothesis.
- Score hypothesis by sum of costs.
- Prune.

**Anchors:**
- If manual anchor exists at frame, force hypothesis to include it, resetting Kalman.
- High weight: cost = 0 for anchor, infinite for others if anchor present? Actually if anchor marked not visible, force missing.

**Missing:**
- If no candidate passes gate, output missing (null).
- After N consecutive misses (e.g., 5), increase search radius, try reacquisition in larger ROI.
- After M misses (e.g., 30 at 60fps = 0.5s), stop track until next anchor or explicit reacquisition trigger.

**Provenance:**
- Each point has provenance enum: detected, manual, predicted, interpolated, artistic.
- Visibility: visible, not_visible, out_of_frame.

## Limitations Documented
- Parallax, zoom, rolling shutter, non-planar scenes break affine model.
- Tiny ball (<3px) unreliable.
- Distractors (white hats, other balls) cause FP.
- Fast motion blur reduces detection.
- Background stabilization is not 3D reconstruction.

## Evaluation (when model adapter added)
- Metrics: visible-frame recall, localization error (px normalized), false positives, hallucinated continuation, fragmentation, reacquisition, required manual corrections.
- Split by recording session, not adjacent frames.
- Report separately: static camera, moving camera, tiny ball, non-visible intervals.
