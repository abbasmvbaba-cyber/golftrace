# Model Card (Placeholder)

**Status:** No real model integrated yet. This document is a template for when a real model is integrated.

## Model Details
- **Model Type:** Small-object center detector / heatmap model for golf ball
- **Version:** 0.0.0 (not yet trained)
- **License:** Unknown - must be verified before commercial use
- **Weights:** No pretrained weight assumed to exist. External weights required.
- **Checksum:** N/A
- **Training Data:** None yet - requires licensed real golf videos with consent

## Intended Use
- Assist golf ball tracking in video
- Preserve source detail using crops/tiles
- Output candidate detections with scores

## Limitations
- Tiny ball (<3px) unreliable
- Distractors (white hats, other balls) cause false positives
- Fast motion blur reduces detection
- Background stabilization is not 3D reconstruction

## Evaluation
- Metrics: visible-frame recall, localization error, false positives, hallucinated continuation, fragmentation, reacquisition, required manual corrections
- Datasets split by recording session, not adjacent frames
- Report separately: static camera, moving camera, tiny ball, non-visible intervals
- No invented benchmark numbers - report only measured results

## Ethical Considerations
- Do not use user videos for training without explicit separate consent
- Check dataset licenses
- Do not describe unverified model as commercially usable

## How to Integrate
1. Place model weights at path specified by MODEL_PATH env var
2. Set MODEL_LICENSE, MODEL_VERSION, MODEL_CHECKSUM env vars
3. Implement actual model loading in backend/app/tracking/model_adapter.py
4. Create model card with real details
5. Run evaluation via backend/app/evaluation/benchmark.py
6. Report results in docs/EVALUATION.md

## Current State
- Model adapter interface implemented in backend/app/tracking/model_adapter.py
- Returns MODEL_NOT_AVAILABLE error when weights not present, offers classical/manual workflow
- No fake model outputs created
