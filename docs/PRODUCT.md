# GolfTrace Product

## Outcome
User can create project, upload golf-shot video, select analysis interval, identify ball in one or more exact frames, request assisted tracking, review missing/uncertain sections, correct track, customize tracer, export MP4.

## Scope
- Asynchronous web app, not real-time camera.
- One golf shot per project initially.
- Manual workflow must work on CPU without pretrained weights.
- Assisted classical tracker second.
- Model adapter later.

## Scientific Honesty
- We estimate 2D trajectory in image coordinates.
- We do NOT claim real-world carry distance, ball speed, spin, launch angle, altitude, true 3D flight from uncalibrated monocular footage.
- Distinguish: detected observations, manual observations, predicted positions, interpolated positions, explicitly artistic positions.
- Missing detection is valid output.
- Plausible parabola != evidence tracking worked.

## Defaults
- Input size limit 500 MiB
- Input duration 60s
- Analysis interval 15s
- Max long edge 3840, short edge 2160
- Supported input FPS up to 120
- Analysis budget 1800 frames
- Export up to 1080p 60 FPS

## User Stories
1. Create project
2. Upload video with progress
3. Preparation status (probing, manifest, preview, thumbnails)
4. Select analysis interval (trim)
5. Navigate exact source frames (frame_index)
6. Add/move ball anchors, mark not visible, out-of-frame
7. Request assisted tracking (uses anchors as constraints)
8. Review missing/uncertain segments
9. Correct track, undo/redo
10. Adjust tracer style
11. Export MP4 with progress and download link

## i18n
- English LTR and Persian RTL via i18n layer.
- No hard-coded scientific claims in marketing text.

## Non-Goals v1
- Real-time tracking
- Multi-ball tracking
- 3D reconstruction
- Automatic distance estimation
