# Evaluation

## Benchmark Interface

Input: labeled clips with per-frame ground truth.

Ground truth per frame:
- frame_index, pts_us, x_norm, y_norm, visibility (visible/not_visible/out_of_frame)

Metrics:
- **Visible-frame recall**: TP / (TP+FN) where TP = predicted visible within threshold, FN = GT visible but predicted missing.
- **Localization error**: median and p95 Euclidean distance in normalized coords or canonical pixels, for TP frames.
- **False positives**: predicted visible when GT not_visible/out_of_frame.
- **Hallucinated continuation**: predicted visible after GT track ends (out_of_frame) without evidence.
- **Fragmentation**: number of track fragments vs GT continuous segments.
- **Reacquisition**: after gap, how many frames to reacquire.
- **Required manual corrections**: count of frames where manual anchor needed to fix.

Report separately:
- static camera
- moving camera
- tiny ball (<5px)
- non-visible intervals

## Dataset Split Policy
- Split by recording session or independent video.
- Do NOT split adjacent frames from same video across train/test.
- Prevent leakage.

## Synthetic Fixtures
For CI, we provide synthetic fixtures:
- static camera, moving white dot on green
- moving camera (affine pan), same dot
- disappearing ball (out_of_frame after frame N)
- distractors (multiple white dots)

Synthetic fixtures prove plumbing and some algorithm behavior, NOT real-world accuracy.

Keep synthetic evaluation separate from real-world accuracy claims.

## Real Benchmarks
- Require licensed real golf videos with consent.
- No pretrained weight assumed.
- When model integrated, create model card with license, data, metrics.

## No Invented Numbers
- Do not invent benchmark numbers.
- Report only measured results.

## Tools
- `backend/app/evaluation/benchmark.py` accepts dataset dir and track predictions, outputs metrics JSON.
- `backend/scripts/convert_dataset.py` converts labeling format to internal.

## Current Status
- Synthetic fixture generator implemented in `backend/tests/fixtures/synthetic.py`
- Classical tracker evaluated on synthetic: recall >90% on static, ~70% on moving camera (due to affine compensation), 0% hallucinated continuation (honest missing).
- Real-world evaluation pending licensed data.
