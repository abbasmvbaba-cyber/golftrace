# Security

## Storage
- Buckets private, no public read.
- Server-generated keys, no user-controlled path traversal.
- Short-lived signed URLs (15 min default) for playback/download.
- Never store signed URLs as persistent identity.

## Upload Validation
- Verify actual object size vs declared.
- Probe media with ffprobe/OpenCV, do not trust MIME or extension.
- Validate: size <=500MiB, duration <=60s, long edge <=3840, short edge <=2160, fps <=120.
- Reject unsupported with actionable error codes.
- Run media parsing/encoding with resource limits, no shell interpolation (no shell=True).

## FFmpeg Hardening
- Restrict protocols: only file, no http/https unless explicitly allowed list.
- No arbitrary network URLs.
- Filesystem access restricted to scratch dirs and object storage temp.
- Resource limits: CPU/memory via cgroups in Docker, timeout per job.

## AuthZ
- Authentication abstraction: DevIdentity vs OIDC.
- Dev auth only when DEV_AUTH_ENABLED=true and ENV=development; production startup rejects unsafe config.
- Validate project ownership on every resource op, including frame retrieval and download link generation.
- Never rely on unguessable ID as authz.

## Quotas & Rate Limits
- Enforce quotas: project count, storage, job concurrency.
- Rate limits per endpoint (see API.md).
- Return 429 with Retry-After.

## Secrets
- No secrets in repo.
- .env.example with placeholders.
- Never log tokens or signed URLs.
- Use environment variables, mounted secrets in prod.

## Containers
- Non-root users.
- Bounded resources (CPU, memory) where practical.
- Read-only root filesystem where possible.

## Deletion
- Project deletion: tombstone, async artifact cleanup job.
- Coordinate deletion with running workers: check tombstone before publishing result, abort if deleted.
- Do not use user videos for model training without explicit separate consent.

## Logging
- Audit events for sensitive actions.
- No PII in logs beyond user_id.

## Dependencies
- Check licenses for library, model, dataset, FFmpeg build.
- Do not describe unverified model as commercially usable.
- Commit lockfiles, choose compatible versions.

## Job Security
- Fencing tokens prevent expired attempt from committing over newer attempt.
- Verify outputs before publishing authoritative result pointer.
- Unique temp keys to avoid race.

## Production Blockers
- Ensure DEV_AUTH_ENABLED=false in prod.
- Ensure Postgres, Redis, MinIO credentials set, not default.
- Ensure HTTPS, CORS restricted.
- Ensure FFmpeg build license compatible (LGPL).
