# Architecture

## Overview
```
[Frontend: React/Vite] --REST /api/v1--> [Backend: FastAPI]
                                          |
                                          +--> [PostgreSQL] (durable truth)
                                          +--> [S3/MinIO] (private buckets)
                                          +--> [Redis] (broker) -> [Celery Workers]
                                          |                           |
                                          |                           +--> FFmpeg/PyAV, OpenCV tracking
                                          +--> Object storage artifacts
```

## Frontend
- React, TypeScript, Vite, Tailwind, TanStack Query, Zustand, Canvas2D
- Stores: project, video, annotation, track, render, ui/i18n
- Components: ProjectList, Uploader, VideoPlayer (preview), ExactFrameViewer, Timeline, TrackOverlay, StyleEditor, ExportDialog
- Utils: geometry.ts centralizes all coordinate transforms (tested)

## Backend
- FastAPI + Pydantic v2
- SQLAlchemy 2.0 + Alembic migrations
- Auth abstraction: DevIdentity (local) vs OIDC adapter (prod)
- Services: upload, media probe, manifest, preview, tracking, rendering, storage, jobs
- Workers: Celery with Redis broker, separate queues: video, cpu_tracking, gpu_tracking, rendering, maintenance
- Video: FFmpeg/ffprobe wrapper with OpenCV fallback for sandbox; PyAV optional
- Tracking: modular interfaces (frame source, candidate detector, camera motion estimator, temporal tracker, gap policy, display-path generator, renderer)

## Storage
- S3-compatible, private buckets
- Server-generated keys: `projects/{project_id}/videos/{video_id}/original/{uuid}.mp4` etc
- No signed URLs stored as persistent identity; generate short-lived on demand
- Large artifacts (manifests, tracks) stored in object storage with schema version header

## Jobs & Reliability
- PostgreSQL is durable source of truth for job state
- Redis not durable DB
- At-least-once delivery, idempotent workers
- Atomic claiming via `SELECT ... FOR UPDATE SKIP LOCKED`, heartbeats, leases, attempt fencing tokens
- Outbox pattern for dispatch recovery
- Reconciler for abandoned jobs
- Per-attempt scratch dirs, unique temp keys, output verification before publishing
- Bounded retries with backoff for transient failures only
- Cancellation checkpoints
- Progress from completed work units

## Security
- Private buckets, short-lived signed links
- Quotas, upload limits, job limits, rate limits
- Verify media, no shell=True, restrict protocols
- Non-root containers, bounded resources
- No logging of tokens/signed URLs
- Project deletion tombstone + async cleanup, coordination with workers

## Data Flow
1. POST /projects -> create project
2. POST /projects/{id}/uploads -> create upload_session, return presigned or direct upload URL (local fallback: direct multipart)
3. POST /uploads/{id}/complete -> verify size, probe media, create video record, queue preparation job
4. Preparation job: frame manifest (pts_us, frame_index), preview transcode, thumbnails, metadata
5. Annotation: POST /videos/{id}/annotation-sets, add annotations (manual observations)
6. Analysis: POST /videos/{id}/analyses (references annotation snapshot, engine config, code version) -> job -> track_version
7. Track revisions: POST /tracks/{id}/revisions
8. Render: POST /tracks/{id}/renders (references track_version + style snapshot) -> job -> MP4 artifact
9. GET /renders/{id}/download -> signed link

## Decisions
- **SQLite fallback for sandbox/tests**: Allows tests without Postgres, but production requires Postgres. Config switches via DATABASE_URL.
- **Filesystem storage fallback**: When S3 env not set, use local directory `.storage` to unblock local manual workflow.
- **Synchronous job fallback**: When Redis/Celery not available, run job inline for tests, but code paths preserve job state in DB for consistency.
- **OpenCV fallback for ffprobe**: Try ffprobe binary first, then PyAV, then OpenCV. OpenCV loses VFR PTS accuracy but allows pipeline to function; we store warning in video metadata and document limitation.
- **Centralized geometry**: All coordinate math in `backend/app/core/geometry.py` and `frontend/src/utils/geometry.ts` with mirrored tests.

## Local Infra
- Docker Compose: postgres:16, redis:7, minio/minio, api (FastAPI), worker (Celery), frontend (Vite dev server)
- MinIO buckets created via entrypoint script
- Alembic migrations run on api startup
