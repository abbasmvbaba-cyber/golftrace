# Data Model

## Entities

### users
- id: uuid pk
- email: unique (nullable for dev)
- display_name
- created_at

### projects
- id: uuid pk
- owner_id: fk users
- title
- description
- status: active/deleted
- deleted_at nullable
- created_at, updated_at
- version (optimistic concurrency)

### videos
- id: uuid pk
- project_id fk
- owner_id
- original_filename
- storage_key: original object key
- size_bytes
- duration_us
- width, height (canonical)
- encoded_width, encoded_height
- rotation: 0/90/180/270
- fps_avg, fps_max, is_vfr boolean
- codec, has_audio
- probe_metadata jsonb
- preparation_status: pending/probing/manifesting/previewing/ready/failed
- preparation_error nullable
- frame_manifest_key nullable
- preview_key nullable
- thumbnail_key nullable
- created_at

### upload_sessions
- id: uuid pk
- project_id fk
- video_id fk nullable (created after complete)
- owner_id
- filename
- size_bytes declared
- storage_key (temp)
- status: created/uploading/completed/failed/aborted
- upload_url (for S3 presigned) nullable
- created_at, expires_at
- idempotency_key unique

### frame_manifests (artifact in object storage, but also metadata row)
- id: uuid pk
- video_id fk
- storage_key
- schema_version
- frame_count
- duration_us
- vfr boolean
- created_at

### annotation_sets
- id: uuid pk
- video_id fk
- owner_id
- version: int
- is_snapshot boolean (immutable snapshot for analysis)
- parent_id nullable (for revision chain)
- created_at
- metadata jsonb (analysis interval start/end frame_index)

### annotations
- id: uuid pk
- annotation_set_id fk
- frame_index int
- x_norm nullable, y_norm nullable
- visibility: visible/not_visible/out_of_frame
- provenance: manual
- created_at
- Note: unavailable coords as null, not zero

### analysis_runs
- id: uuid pk
- video_id fk
- annotation_set_snapshot_id fk
- owner_id
- engine: classical/model
- engine_config jsonb
- code_version
- model_version nullable, model_checksum nullable
- status: queued/running/succeeded/failed/cancelled
- job_id fk
- track_version_id fk nullable
- created_at

### track_versions
- id: uuid pk
- video_id fk
- analysis_run_id fk nullable (null for manual)
- parent_id nullable (for manual revisions)
- owner_id
- storage_key (track artifact)
- schema_version
- frame_count
- provenance_summary jsonb
- created_at
- is_manual boolean

Track artifact JSON:
```json
{
  "schema_version": 1,
  "video_id": "...",
  "track_version_id": "...",
  "points": [
    {"frame_index": 0, "pts_us": 0, "x_norm": 0.5, "y_norm": 0.5, "provenance": "manual", "visibility": "visible", "score": 1.0, "is_anchor": true},
    {"frame_index": 1, "pts_us": 16666, "x_norm": null, "y_norm": null, "provenance": "predicted", "visibility": "not_visible", "score": null}
  ],
  "camera_motion": {"segments": [...], "transforms": [...]},
  "gap_policy": {"max_gap_ms": 100}
}
```

### render_jobs / renders
- id: uuid pk
- track_version_id fk
- owner_id
- video_id fk
- style_snapshot jsonb
- status: queued/running/succeeded/failed/cancelled
- job_id fk
- output_storage_key nullable
- output_metadata jsonb (width,height,fps,duration,codec)
- created_at

### jobs
- id: uuid pk
- type: video_preparation / tracking / rendering / cleanup / maintenance
- owner_id nullable
- project_id nullable
- video_id nullable
- status: queued/claimed/running/succeeded/failed/cancelled
- attempt: int
- max_attempts: int
- lease_expires_at nullable
- claimed_by nullable (worker id)
- fencing_token: uuid
- progress jsonb
- error_code nullable, error_message nullable
- created_at, updated_at, started_at, finished_at
- idempotency_key unique

### outbox_events
- id: uuid pk
- aggregate_type, aggregate_id
- event_type
- payload jsonb
- status: pending/dispatched/failed
- created_at, dispatched_at
- attempt

### audit_events
- id: uuid pk
- user_id
- project_id nullable
- action
- resource_type, resource_id
- metadata jsonb
- created_at

## Migrations
- Alembic, with initial migration creating all tables.
- Use uuid type, jsonb for metadata.

## Immutability
- Annotation sets: snapshot semantics. When analysis requested, create immutable snapshot copy.
- Track versions: immutable. Revisions create new version with parent_id.
- Render references specific track version + style snapshot, immutable.

## No Signed URLs as Identity
- Store storage_key only. Generate signed URL on demand for download/playback with short expiry.

## Large Artifacts
- Frame manifests, tracks stored in object storage with schema_version, not in DB jsonb beyond summary.
