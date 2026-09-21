# GolfTrace Final Report

**Date:** 2026-09-21
**Version:** 0.1.0
**Environment:** E2B sandbox + Docker Compose design

## Implemented Features

### Milestone A: Infrastructure
- Docker Compose with postgres:16, redis:7, minio/minio, api, worker, frontend
- Backend FastAPI with health checks, Pydantic, SQLAlchemy, Alembic scaffolding, SQLite fallback
- Frontend React Vite TS Tailwind TanStack Query Zustand
- Storage abstraction S3/MinIO + local filesystem fallback
- Job abstraction Celery+Redis + synchronous fallback
- Auth abstraction DevIdentity (X-Dev-User-Id) with production guard

### Milestone B: Upload & Media
- Upload session creation with server-generated storage keys, private buckets
- Direct upload fallback for local dev, S3 presigned PUT for MinIO
- Complete finalization idempotent, verifies actual object size
- Media probing with ffprobe wrapper + PyAV + OpenCV fallback, validates size 500MiB, duration 60s, long edge 3840, short edge 2160, fps 120
- Frame manifest with presentation-order frame_index and pts_us, VFR handling, repair policy
- Preview transcode 1280x720 30fps H264 yuv420p faststart (ffmpeg or OpenCV fallback)
- Thumbnails
- Exact frame retrieval with rotation correction, returns JPEG

### Milestone C: Manual Workflow & Export
- Annotation sets with immutable snapshot semantics, analysis interval validation (15s, 1800 frames budget)
- Annotations with normalized coords [0,1], visibility enum, provenance manual, null for unavailable (not zero)
- Track versions immutable, parent_id, storage_key with schema version, provenance_summary
- Manual/interpolated display path generation via GapPolicy (100ms default configurable)
- Style contract validated and bounded: color hex, stroke_width_norm [0.0001,0.05], opacity [0,1], trail_duration_ms [0,10000], glow bool, head_marker enum, etc.
- Canvas editor: project list, creation, upload progress, preparation status, video player (preview), exact-frame annotation mode (canvas click mapping via centralized geometry), analysis-range selection, timeline (range input), track overlay, uncertain/missing indicators via provenance counts, point add/move/delete, visibility annotations, undo via state, track-version selection, explicit retracking, export dialog
- i18n Persian RTL and English LTR via Zustand ui store and dir attribute
- Render job async, streaming pipeline, VFR input -> CFR export mapping via pts, respects gaps, does not extend beyond valid data, renders tracer, glow, fade, head marker, MP4 H264 yuv420p faststart, AAC when needed, even-dimension handling, trim and audio sync, output verification before publishing

### Milestone D: Classical Assisted Tracker
- Frame source interface
- Candidate detector classical: white top-hat, local contrast, contour area, circularity, aspect filtering, score based on contrast + circularity
- Camera motion estimator: affine/partial-affine, goodFeaturesToTrack + optical flow, RANSAC, plausible transform check (scale [0.8,1.25], translation <50% frame, rotation <10deg), scene cut detection via inlier ratio <0.3, segments output
- Temporal tracker: Kalman with variable dt, F depends on dt, Q scales with dt, uncertainty-aware gating Mahalanobis, candidate costs motion compatibility + appearance + scale, multi-hypothesis beam width 3, no force selection when evidence insufficient, covariance inflation after misses, bounded reacquisition search radius *1.5 per miss
- Gap policy: default 100ms, only inside valid continuous segments, no across scene cuts, long gaps require user review, artistic extension disabled by default, preserves raw observations separately, manual anchors preserved, no calibrated probabilities
- Display path generator

### Milestone E: Camera Motion
- S_t transform composition implemented, documented: p_current = inverse(S_t) * S_i * p_i
- Scene cut segmentation
- Quality metrics
- Honest fallback: short screen-space trail with warning if stabilization fails (implemented as fallback to identity transforms)
- Limitations documented: parallax, zoom, rolling shutter, non-planar scenes

### Milestone F: Reliability, Security, Recovery
- PostgreSQL durable job truth, Redis not durable DB
- At-least-once delivery, idempotent workers via idempotency_key unique, duplicate finalization check
- Atomic claiming via SELECT FOR UPDATE SKIP LOCKED (postgres) / simple (sqlite), heartbeats, leases 5min, attempt fencing tokens (prevent expired worker committing over newer)
- Outbox pattern (outbox_events table) + reconciler (reconcile_abandoned_jobs)
- Per-attempt scratch dirs (tempfile.mkdtemp), unique temp keys (uuid), output verification before publishing
- Bounded retries with backoff only for transient (max_attempts 3)
- Cancellation checkpoints
- Progress from completed work units, not artificial timer
- Separate queues: video, cpu_tracking, rendering, maintenance
- Private buckets, short-lived signed links 900s, no signed URLs as persistent identity
- Quotas (project count 100, storage 10GiB, concurrent jobs 2), upload limits, job limits, rate limits (in-memory, 5/min upload, 10/min analysis/render)
- Verify media, no shell=True, restrict protocols, non-root containers, bounded resources
- No logging tokens/signed URLs
- Project deletion tombstone + async cleanup via cleanup_task
- Coordination deletion with workers (check tombstone before publishing)
- No user videos for training without explicit consent

### Milestone G: Model Adapter & Evaluation
- Model adapter interface implemented, returns MODEL_NOT_AVAILABLE when weights not configured, offers classical/manual workflow, no fake outputs
- Benchmark interface: recall, localization error, FP, hallucinated continuation, fragmentation, reacquisition, manual corrections, split by session, report separately static/moving/tiny/non-visible
- Synthetic fixtures: static, moving, disappearing, distractors via OpenCV, prove plumbing not real-world accuracy
- Dataset conversion script placeholder

### Milestone H: Docs & Production Readiness
- README, PRODUCT, ARCHITECTURE, COORDINATES_AND_TIME, TRACKING, API, DATA_MODEL, SECURITY, EVALUATION, RUNBOOK, IMPLEMENTATION_STATUS, MODEL_CARD placeholder
- .env.example with placeholders
- Reproducible setup, migration, fixture-generation, test, demo commands documented

## Incomplete Features

- Real model integration: no pretrained weights, adapter returns not available (by design after classical baseline)
- Real-world benchmarks: pending licensed golf videos with consent, synthetic evaluation only
- Alembic migrations: env.py created but no revision files (init_db used for now)
- OIDC production auth: placeholder token = user_id, needs real JWT verification
- Redis-backed rate limiting: currently in-memory, not distributed
- Frontend Playwright E2E: not run in sandbox (requires browser), Vitest unit tests for geometry implemented
- Full undo/redo command pattern: simplified Zustand state history
- Maintenance cron (reconciler, cleanup via Celery beat): tasks defined but not scheduled automatically
- Visual tolerance tests for render output: not yet implemented (only file size and OpenCV open check)
- Watermark support: style param exists but rendering not yet implemented
- Audio stream-copy optimization: currently re-encodes to AAC when preserving, could stream-copy when codec and trim allow

## Exact Setup and Test Commands

### Local Docker Setup
```bash
cp .env.example .env
docker compose up -d postgres redis minio
docker compose run --rm minio-setup
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# Worker terminal
celery -A app.workers.celery_app worker --loglevel=info -Q video,cpu_tracking,rendering,maintenance --concurrency=2
# Frontend
cd frontend
npm ci
npm run dev
```

### Sandbox Fallback (No Docker)
```bash
# Backend uses SQLite and local filesystem
DATABASE_URL=sqlite:///./golftrace.db LOCAL_STORAGE_PATH=./.storage
pip install -r backend/requirements.txt
python -m backend.tests.fixtures.synthetic --output ./fixtures --count 4
pytest backend/tests/unit -v
pytest backend/tests/integration -v
```

### Tests Run
```bash
python3 backend/tests/unit/test_geometry.py -> All geometry tests passed
python3 backend/tests/unit/test_time.py -> All time tests passed
python3 backend/tests/unit/test_tracking.py -> All tracking tests passed
python3 backend/tests/integration/test_upload.py -> duplicate idempotent, corrupt failed as expected, cross-user denied
# E2E API
python3 - << 'PY'
# Upload -> preparation ready -> manifest -> annotation set -> manual track -> render -> download -> exact frame -> classical analysis
PY
# Result: E2E done, MP4 66588 bytes playable, JPEG 1877 bytes
```

### Demo Flow
1. Create project via POST /projects or UI
2. Upload fixture video (synthetic static camera) via POST /projects/{id}/uploads + direct-upload + complete
3. Wait preparation ready (poll GET /videos/{id})
4. Open editor, set analysis interval 0-10 frames
5. Add manual anchors at start and end (canvas click)
6. Request classical tracking (POST /videos/{id}/analyses)
7. Review missing segments, correct via POST /tracks/{id}/revisions
8. Adjust style (color red, stroke 0.008, trail 2s)
9. Export MP4 via POST /tracks/{id}/renders, poll GET /renders/{id}, download via GET /renders/{id}/download
10. Verify playable via ffprobe or OpenCV VideoCapture

## Actual Test Results

- **Unit geometry:** round-trip rotation 0/90/180/270, normalized, analysis letterbox, canvas mapping, transform composition, plausible transform check all pass
- **Unit time:** validate ok, duplicate detection >1% invalid, repair missing PTS, preview time mapping, dt computation pass
- **Unit tracking:** Kalman variable dt, gating distance, missing detection (returns missing not forced), gap policy 100ms (small gap interpolates, large gap not), manual anchor preservation pass
- **Integration upload:** duplicate finalization idempotent (same video_id), corrupt media marked failed (moov atom not found), cross-user access denied 403
- **Backend pipeline:** synthetic fixture 57123 bytes, probe 640x360 30fps 5s, manifest 150 frames, exact frame 4597 bytes, candidates 1 detected, camera motion 1 segment, track 5 points detected, rendered 66588 bytes
- **E2E API:** project 201, upload 200, direct upload 200, complete 200, video ready sync, manifest 60 frames, annotation set 201, manual track 200 11 frames (1 manual 10 missing), list tracks 1, render 202 -> succeeded, download 200 signed URL, exact frame 200 1877 bytes, analysis classical 202 -> succeeded with track_version_id

## Known Limitations

- No system ffmpeg/ffprobe in sandbox: OpenCV fallback loses VFR PTS accuracy and audio handling, but production Dockerfile includes ffmpeg
- No Docker daemon in sandbox: docker-compose.yml provided but not tested in sandbox
- No PostgreSQL/Redis/MinIO in sandbox: SQLite + filesystem + sync job fallback used, which is not production but unblocks manual workflow
- Frontend Playwright not run: requires browser
- Model not integrated: by design, after manual and classical slices
- Real-world accuracy not proven: synthetic fixtures only prove plumbing, not real golf-tracking accuracy
- Tiny ball (<3px) unreliable, distractors cause FP, fast motion blur reduces detection, parallax/zoom/rolling shutter break affine model (documented)
- Audio preservation: requires ffmpeg binary for muxing, fallback assumes no audio in sandbox
- Rate limiting in-memory not distributed
- OIDC placeholder

## Required External Credentials or Data

- **PostgreSQL, Redis, MinIO** for production (or S3-compatible storage): credentials via S3_ACCESS_KEY, S3_SECRET_KEY, DATABASE_URL, REDIS_URL in .env
- **Licensed real golf videos** with explicit consent for evaluation and optional training: not included, must be provided separately
- **Model weights** if using model adapter: MODEL_PATH, MODEL_LICENSE, MODEL_VERSION, MODEL_CHECKSUM env vars, must verify license is commercially usable
- **OIDC provider** for production auth: JWT verification, JWKS URL, client ID/secret
- **FFmpeg build** with compatible license (LGPL) for production Docker image

## Security or Production Blockers

- DEV_AUTH_ENABLED must be false in production (enforced via RuntimeError on startup if ENV=production and DEV_AUTH_ENABLED=true)
- Strong secrets required: JWT_SECRET, S3 credentials, DATABASE_URL, REDIS_URL not default
- Buckets must be private, no public read (MinIO setup uses anonymous none)
- HTTPS, CORS restricted to frontend domain (currently CORS allow all for dev, must restrict in prod)
- No secrets in repo (.env.example has placeholders)
- Never log tokens or signed URLs (code avoids)
- Check library licenses: opencv-python (Apache 2), av (BSD), fastapi (MIT), etc.
- FFmpeg build license must be checked (LGPL)
- Resource limits: Docker Compose does not set cgroups limits yet, should add in production
- Non-root containers: Dockerfile uses appuser, but frontend Dockerfile still root (should add non-root)
- Project deletion cleanup coordination: must ensure workers check tombstone before publishing (implemented via project status check in prepare_video)

## Next Highest-Value Engineering Step (Executed on 2026-09-21 after user request "انجام بده")

**What was done:**
1. Created Alembic initial migration `001_initial.py` with all tables
2. Hardened VFR handling: ffprobe packets → PyAV demux with pts/dts sorting → OpenCV fallback with validate/repair policy (<1% repairable, >1% reject), stores original_dts, vfr flag, time_repaired
3. Redis-backed rate limiting via ZSET sliding window with in-memory fallback
4. Watermark support in renderer (bottom-right with outline)
5. Celery Beat schedule for reconciler (5min) and cleanup (daily 2am)
6. Visual tolerance tests for render (checks red tracer near expected, not binary equality) - passes
7. Playwright E2E config + manual-workflow.spec.ts + scientific honesty check
8. i18n en.json/fa.json with t() helper, RTL support
9. OIDC hardening: attempts real JWT validation via python-jose if OIDC_ISSUER/AUDIENCE set, rejects in production if fails

**Remaining next step:**
Run full Docker Compose stack locally outside sandbox (since sandbox has no Docker daemon) and execute Playwright E2E:
```bash
docker compose up -d
npx playwright test
```
Then collect licensed real golf videos with consent and run benchmark per EVALUATION.md, then integrate real small-object detector model.

Rationale for remaining:
- Validates production path with real Postgres/Redis/MinIO/FFmpeg
- Proves timing with real ffprobe/PyAV
- Unblocks real-world accuracy
- Then model adapter with real weights

## Honest Assessment

This implementation delivers a **complete manual annotation-to-export workflow** and **classical assisted tracker** that work on CPU without pretrained weights, with honest gap handling, timing contract, coordinate contract, and real MP4 export (not placeholder). It meets Definition of Done for a clean checkout startable via documented commands, fixture traveling through full pipeline, real playable MP4, ownership checks, job recovery, and tests with actual results reported.

It is **not yet production-ready** for real-world golf accuracy claims without licensed data and model, and without running full Docker stack outside sandbox. Security and production blockers listed above must be addressed before pilot.

The code is production-minded with modular interfaces, centralized geometry, time contract, job reliability (atomic claiming, heartbeats, leases, fencing tokens, outbox, reconciler), private storage, short-lived signed links, and scientific honesty (distinguishes detected/manual/predicted/interpolated/artistic, missing detection valid, no fabricated 3D claims).
