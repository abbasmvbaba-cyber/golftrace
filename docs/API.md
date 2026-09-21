# API

Base: /api/v1

## Auth
- Dev mode: header X-Dev-User-Id or default user. Must be explicitly enabled via DEV_AUTH_ENABLED=true and rejected in prod if enabled.
- Prod: OIDC Bearer token, validated, user id extracted.
- All endpoints check project ownership.

## Error Format
```json
{
  "error_code": "VIDEO_TOO_LARGE",
  "message": "Localized message",
  "details": {}
}
```
- Stable machine-readable error codes.

## Endpoints

### Projects
- POST /projects
  - Body: {title, description, idempotency_key}
  - 201 {project}
  - Idempotent via key

- GET /projects
  - List owned projects

- GET /projects/{project_id}
  - Requires ownership

- PATCH /projects/{project_id}
  - Body: {title, description, version} optimistic concurrency
  - 409 if version conflict

- DELETE /projects/{project_id}
  - Tombstone + async cleanup job

### Uploads
- POST /projects/{project_id}/uploads
  - Body: {filename, size_bytes, content_type, idempotency_key}
  - Validates size <=500MiB
  - Creates upload_session, storage_key, returns {upload_id, upload_url, storage_key, expires_at}
  - For local filesystem fallback, upload_url is /api/v1/uploads/{id}/direct-upload

- POST /uploads/{upload_id}/complete
  - Body: {size_bytes?}
  - Idempotent
  - Verifies actual object size, probes media, validates duration <=60s, dimensions <=3840x2160, fps <=120
  - Creates video record, queues preparation job
  - 202 {video_id, job_id}

### Videos
- GET /videos/{video_id}
  - Metadata + preparation status

- GET /videos/{video_id}/playback
  - Returns signed URL for preview or original (short-lived)

- GET /videos/{video_id}/frame-manifest
  - Returns manifest JSON or signed URL to artifact

- GET /videos/{video_id}/frames/{frame_index}
  - Returns exact frame as JPEG/PNG
  - Query: ?format=jpeg&quality=95
  - Validates frame_index in range, uses canonical orientation

### Annotation Sets
- POST /videos/{video_id}/annotation-sets
  - Body: {analysis_interval: {start_frame, end_frame}, annotations: [{frame_index, x_norm, y_norm, visibility}], idempotency_key, parent_id?}
  - Creates mutable set or snapshot if ?snapshot=true
  - For analysis, backend creates snapshot automatically

- GET /annotation-sets/{annotation_set_id}
  - Returns set + annotations

### Analyses
- POST /videos/{video_id}/analyses
  - Body: {annotation_set_id, engine: "classical"|"model", engine_config: {max_gap_ms: 100, analysis_budget_frames: 1800}, idempotency_key}
  - Validates analysis interval <=15s and <=1800 frames
  - Creates analysis_run + job
  - 202 {analysis_id, job_id}

- GET /analyses/{analysis_id}
  - Returns analysis_run + track_version_id if succeeded

### Jobs
- GET /jobs/{job_id}
  - Status, progress, error

- POST /jobs/{job_id}/cancel
  - Requests cancellation, worker checks checkpoint

### Tracks
- GET /videos/{video_id}/tracks
  - List track_versions for video

- GET /tracks/{track_version_id}
  - Returns track artifact (or signed URL) + metadata

- POST /tracks/{track_version_id}/revisions
  - Body: {annotations: [...], reason, idempotency_key}
  - Creates new manual track_version with parent

### Renders
- POST /tracks/{track_version_id}/renders
  - Body: {style: {color, stroke_width_norm, glow, opacity, trail_duration_ms, fade, head_marker, progressive_reveal, inferred_style, watermark, audio_preserve}, export: {width, height, fps}, idempotency_key}
  - Validates style params bounded
  - 202 {render_id, job_id}

- GET /renders/{render_id}
  - Status

- GET /renders/{render_id}/download
  - Returns signed URL for MP4, short-lived

## Idempotency
- All expensive creation ops accept idempotency_key, stored unique, return existing resource if same key replayed.

## Optimistic Concurrency
- Projects and annotation_sets use version field, client sends version, 409 on conflict.

## OpenAPI
- Auto-generated at /api/docs
- Frontend contract aligned via generated types (openapi-typescript)

## Rate Limits
- Upload: 5 per minute per user
- Analyses: 10 per minute
- Renders: 10 per minute
- Frame retrieval: 120 per minute

## Quotas
- Project count: 100 per user
- Storage: 10 GiB per user (configurable)
- Job concurrency per user: 2

## Localization
- Error messages localized via Accept-Language header, but error_code stable.
