# GolfTrace

Production-minded, assisted golf-ball video tracking and shot-tracer web application.

## Outcome
User can create project, upload golf-shot video, select analysis interval, identify ball in exact frames, request assisted tracking, review missing/uncertain sections, correct track, customize tracer, export playable MP4.

First release is asynchronous web app, not real-time camera. Supports Persian RTL and English LTR.

## Scientific Honesty
- Estimates 2D trajectory in image coordinates only.
- Does NOT claim real-world carry distance, ball speed, spin, launch angle, altitude, or true 3D flight from uncalibrated monocular footage.
- Distinguishes: detected observations, manual observations, predicted positions, interpolated positions, explicitly artistic positions.
- Missing detection is valid output.
- Plausible parabola is not evidence tracking worked.

## Tech Stack
- Frontend: React, TypeScript, Vite, Tailwind, TanStack Query, Zustand, Canvas 2D
- Backend: Python, FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL
- Workers: Celery with Redis
- Storage: S3-compatible (MinIO local)
- Video: FFmpeg, ffprobe, PyAV, OpenCV fallback
- Tracking: OpenCV, NumPy, SciPy
- Testing: pytest, Vitest, Playwright
- Infra: Docker Compose

## Quick Start (Docker)

```bash
cp .env.example .env
docker compose up -d postgres redis minio
docker compose run --rm minio-setup
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# Worker in another terminal
celery -A app.workers.celery_app worker --loglevel=info -Q video,cpu_tracking,rendering,maintenance

# Frontend
cd frontend
npm ci
npm run dev
```

URLs:
- Frontend: http://localhost:5173
- API: http://localhost:8000/api/docs
- MinIO: http://localhost:9001

## Local Fallback (Sandbox / No Docker)

Backend supports SQLite and local filesystem storage when Postgres/S3/Redis unavailable:
- DATABASE_URL=sqlite:///./golftrace.db
- LOCAL_STORAGE_PATH=./.storage
- Celery tasks run synchronously if Redis not reachable

This unblocks manual annotation-to-export workflow without Docker.

## API

Base: /api/v1

See docs/API.md for full list.

Key endpoints:
- POST /projects
- POST /projects/{id}/uploads + POST /uploads/{id}/complete
- GET /videos/{id}, /playback, /frame-manifest, /frames/{index}
- POST /videos/{id}/annotation-sets
- POST /videos/{id}/analyses
- GET /jobs/{id}
- GET /videos/{id}/tracks, GET /tracks/{id}, POST /tracks/{id}/revisions
- POST /tracks/{id}/renders, GET /renders/{id}, /download

## Coordinate & Time Contract

See docs/COORDINATES_AND_TIME.md

- Canonical annotation coordinate system is orientation-corrected display frame, normalized [0,1]
- Centralized geometry utilities in backend/app/core/geometry.py and frontend/src/utils/geometry.ts
- Time: pts_us presentation order, variable dt, VFR handling, repair policy documented

## Tracking

See docs/TRACKING.md

- Modular interfaces: frame source, candidate detector, camera motion estimator, temporal tracker, gap policy, display-path generator, renderer
- Classical detector: white top-hat, LoG, motion cues, bounded search
- Kalman with variable dt, gating, multi-hypothesis beam
- Gap policy: default 100ms, only inside valid segments, no across scene cuts
- Camera motion: affine/partial-affine RANSAC, scene cut detection, S_t composition: p_current = inv(S_t) * S_i * p_i

## Data Model

See docs/DATA_MODEL.md

Immutable annotation snapshots, immutable track versions, render references track + style snapshot.

## Security

See docs/SECURITY.md

Private buckets, short-lived signed URLs, ownership checks, quotas, rate limits, no shell=True, project deletion tombstone + async cleanup.

## Testing

```bash
# Backend unit
pytest backend/tests/unit -v

# Generate fixtures
python -m backend.tests.fixtures.synthetic --output ./fixtures --count 4

# Frontend
cd frontend && npm run test

# E2E (needs stack)
cd frontend && npx playwright test
```

## Evaluation

See docs/EVALUATION.md

Benchmark interface reports recall, localization error, FP, hallucinated continuation, fragmentation, reacquisition, manual corrections. Split by session, not adjacent frames.

## Documentation

- docs/PRODUCT.md
- docs/ARCHITECTURE.md
- docs/COORDINATES_AND_TIME.md
- docs/TRACKING.md
- docs/API.md
- docs/DATA_MODEL.md
- docs/SECURITY.md
- docs/EVALUATION.md
- docs/RUNBOOK.md
- docs/IMPLEMENTATION_STATUS.md

## Implementation Status

See docs/IMPLEMENTATION_STATUS.md for milestone progress and honest report.

## Definition of Done

- Clean checkout can start via documented commands
- Fixture can travel through upload → exact-frame annotation → track creation → editing → rendering → download
- Output is real playable MP4, not placeholder
- Manual mode and classical baseline work without trained model
- Track gaps honest and visible
- Timing and orientation correct
- Artifacts and revisions reproducible
- Ownership checks, bounded processing, job recovery, cleanup exist
- Tests run and actual results reported

## License

Check library, model, dataset, FFmpeg build licenses. No pretrained weight assumed to exist. Do not describe unverified model as commercially usable.
