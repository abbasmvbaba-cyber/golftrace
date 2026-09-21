# Runbook

## Local Setup (Docker Compose)

### Prerequisites
- Docker, Docker Compose v2
- Node 20+, Python 3.11+
- Make

### Steps
```bash
cp .env.example .env
# Edit .env for local dev

docker compose up -d postgres redis minio
# Wait for healthy

# Create MinIO buckets
docker compose run --rm minio-setup

# Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# In another terminal, worker
celery -A app.workers.celery_app worker --loglevel=info -Q video,cpu_tracking,rendering,maintenance

# Frontend
cd frontend
npm ci
npm run dev -- --host 0.0.0.0 --port 5173
```

### URLs
- Frontend: http://localhost:5173
- API: http://localhost:8000/api/v1
- API Docs: http://localhost:8000/api/docs
- MinIO Console: http://localhost:9001 (minioadmin/minioadmin)
- Postgres: localhost:5432
- Redis: localhost:6379

## Environment Variables
See .env.example. Key vars:
- DATABASE_URL
- REDIS_URL
- S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET, S3_REGION
- DEV_AUTH_ENABLED (true for local)
- ENV (development/production)
- MAX_UPLOAD_SIZE, MAX_DURATION, etc

## Migrations
```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic downgrade -1
```

## Fixture Generation
```bash
python -m backend.tests.fixtures.synthetic --output ./fixtures --count 4
```

## Tests
```bash
# Backend unit
pytest backend/tests/unit -v

# Backend integration (needs DB)
pytest backend/tests/integration -v

# Frontend unit
cd frontend && npm run test

# E2E (needs running stack)
cd frontend && npx playwright test
```

## Demo Flow
1. Create project via UI
2. Upload fixture video (synthetic static camera)
3. Wait preparation ready
4. Open editor, set analysis interval 0-5s
5. Add manual anchors at start and end
6. Request classical tracking
7. Review missing segments, correct
8. Adjust style (color red, stroke 0.008, trail 2s)
9. Export MP4, download, verify playable

## Troubleshooting
- **FFmpeg not found**: Ensure ffmpeg installed in api/worker images (Dockerfile includes)
- **MinIO connection failed**: Check S3_ENDPOINT, bucket exists, credentials
- **Job stuck queued**: Check Redis, Celery worker running, check jobs table lease_expires_at, run reconciler
- **Frame retrieval 404**: Check manifest exists, frame_index in range, video preparation status ready
- **Render fails even dimensions**: Ensure export width/height even, code handles padding
- **Auth 403**: Check project ownership, Dev auth enabled in dev
- **Out of storage**: Check quotas, cleanup deleted projects via maintenance queue

## Production Checks
- DEV_AUTH_ENABLED=false
- ENV=production
- Strong secrets, not default
- Postgres, Redis, S3 production endpoints
- HTTPS, CORS restricted to frontend domain
- Resource limits set
- FFmpeg build license checked
- No secrets in logs

## Maintenance Jobs
- Reconciler: runs every 5 min, finds abandoned jobs (lease expired) and re-queues
- Cleanup: deletes artifacts for tombstoned projects after 7 days
- Outbox dispatcher: dispatches pending outbox_events

## Scaling
- Start GPU concurrency conservatively (1 per GPU)
- Separate queues: video (CPU), cpu_tracking, gpu_tracking, rendering
- Worker autoscale based on queue length
