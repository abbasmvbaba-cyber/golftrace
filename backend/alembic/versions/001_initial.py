"""Initial migration - all tables

Revision ID: 001_initial
Revises: 
Create Date: 2026-09-21

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # users
    op.create_table('users',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('display_name', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )
    # projects
    op.create_table('projects',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('owner_id', sa.String(length=36), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_projects_owner_id'), 'projects', ['owner_id'], unique=False)

    # videos
    op.create_table('videos',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('owner_id', sa.String(length=36), nullable=False),
        sa.Column('original_filename', sa.String(length=512), nullable=False),
        sa.Column('storage_key', sa.String(length=1024), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('duration_us', sa.BigInteger(), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('encoded_width', sa.Integer(), nullable=True),
        sa.Column('encoded_height', sa.Integer(), nullable=True),
        sa.Column('rotation', sa.Integer(), nullable=False),
        sa.Column('fps_avg', sa.Float(), nullable=True),
        sa.Column('fps_max', sa.Float(), nullable=True),
        sa.Column('is_vfr', sa.Boolean(), nullable=False),
        sa.Column('codec', sa.String(length=64), nullable=True),
        sa.Column('has_audio', sa.Boolean(), nullable=False),
        sa.Column('probe_metadata', sa.JSON(), nullable=True),
        sa.Column('preparation_status', sa.String(length=30), nullable=False),
        sa.Column('preparation_error', sa.Text(), nullable=True),
        sa.Column('frame_manifest_key', sa.String(length=1024), nullable=True),
        sa.Column('preview_key', sa.String(length=1024), nullable=True),
        sa.Column('thumbnail_key', sa.String(length=1024), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_videos_owner_id'), 'videos', ['owner_id'], unique=False)
    op.create_index(op.f('ix_videos_project_id'), 'videos', ['project_id'], unique=False)

    # frame_manifests
    op.create_table('frame_manifests',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('video_id', sa.String(length=36), nullable=False),
        sa.Column('storage_key', sa.String(length=1024), nullable=False),
        sa.Column('schema_version', sa.Integer(), nullable=False),
        sa.Column('frame_count', sa.Integer(), nullable=False),
        sa.Column('duration_us', sa.BigInteger(), nullable=False),
        sa.Column('vfr', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_frame_manifests_video_id'), 'frame_manifests', ['video_id'], unique=False)

    # upload_sessions
    op.create_table('upload_sessions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('video_id', sa.String(length=36), nullable=True),
        sa.Column('owner_id', sa.String(length=36), nullable=False),
        sa.Column('filename', sa.String(length=512), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('storage_key', sa.String(length=1024), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('upload_url', sa.String(length=1024), nullable=True),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_upload_sessions_idempotency_key'), 'upload_sessions', ['idempotency_key'], unique=True)
    op.create_index(op.f('ix_upload_sessions_project_id'), 'upload_sessions', ['project_id'], unique=False)

    # jobs (must be before analysis_runs and render_jobs)
    op.create_table('jobs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('type', sa.String(length=30), nullable=False),
        sa.Column('owner_id', sa.String(length=36), nullable=True),
        sa.Column('project_id', sa.String(length=36), nullable=True),
        sa.Column('video_id', sa.String(length=36), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('attempt', sa.Integer(), nullable=False),
        sa.Column('max_attempts', sa.Integer(), nullable=False),
        sa.Column('lease_expires_at', sa.DateTime(), nullable=True),
        sa.Column('claimed_by', sa.String(length=128), nullable=True),
        sa.Column('fencing_token', sa.String(length=36), nullable=False),
        sa.Column('progress', sa.JSON(), nullable=True),
        sa.Column('error_code', sa.String(length=64), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_jobs_idempotency_key'), 'jobs', ['idempotency_key'], unique=True)

    # annotation_sets
    op.create_table('annotation_sets',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('video_id', sa.String(length=36), nullable=False),
        sa.Column('owner_id', sa.String(length=36), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('is_snapshot', sa.Boolean(), nullable=False),
        sa.Column('parent_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['parent_id'], ['annotation_sets.id'], ),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_annotation_sets_video_id'), 'annotation_sets', ['video_id'], unique=False)

    # annotations
    op.create_table('annotations',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('annotation_set_id', sa.String(length=36), nullable=False),
        sa.Column('frame_index', sa.Integer(), nullable=False),
        sa.Column('x_norm', sa.Float(), nullable=True),
        sa.Column('y_norm', sa.Float(), nullable=True),
        sa.Column('visibility', sa.String(length=20), nullable=False),
        sa.Column('provenance', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['annotation_set_id'], ['annotation_sets.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_annotations_annotation_set_id'), 'annotations', ['annotation_set_id'], unique=False)
    op.create_index(op.f('ix_annotations_frame_index'), 'annotations', ['frame_index'], unique=False)

    # track_versions
    op.create_table('track_versions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('video_id', sa.String(length=36), nullable=False),
        sa.Column('analysis_run_id', sa.String(length=36), nullable=True),
        sa.Column('parent_id', sa.String(length=36), nullable=True),
        sa.Column('owner_id', sa.String(length=36), nullable=False),
        sa.Column('storage_key', sa.String(length=1024), nullable=False),
        sa.Column('schema_version', sa.Integer(), nullable=False),
        sa.Column('frame_count', sa.Integer(), nullable=False),
        sa.Column('provenance_summary', sa.JSON(), nullable=True),
        sa.Column('is_manual', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['analysis_run_id'], ['analysis_runs.id'], ),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['parent_id'], ['track_versions.id'], ),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_track_versions_video_id'), 'track_versions', ['video_id'], unique=False)

    # analysis_runs
    op.create_table('analysis_runs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('video_id', sa.String(length=36), nullable=False),
        sa.Column('annotation_set_snapshot_id', sa.String(length=36), nullable=False),
        sa.Column('owner_id', sa.String(length=36), nullable=False),
        sa.Column('engine', sa.String(length=20), nullable=False),
        sa.Column('engine_config', sa.JSON(), nullable=True),
        sa.Column('code_version', sa.String(length=64), nullable=True),
        sa.Column('model_version', sa.String(length=64), nullable=True),
        sa.Column('model_checksum', sa.String(length=128), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('job_id', sa.String(length=36), nullable=True),
        sa.Column('track_version_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['annotation_set_snapshot_id'], ['annotation_sets.id'], ),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['track_version_id'], ['track_versions.id'], ),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_analysis_runs_video_id'), 'analysis_runs', ['video_id'], unique=False)

    # render_jobs
    op.create_table('render_jobs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('track_version_id', sa.String(length=36), nullable=False),
        sa.Column('owner_id', sa.String(length=36), nullable=False),
        sa.Column('video_id', sa.String(length=36), nullable=False),
        sa.Column('style_snapshot', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('job_id', sa.String(length=36), nullable=True),
        sa.Column('output_storage_key', sa.String(length=1024), nullable=True),
        sa.Column('output_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['track_version_id'], ['track_versions.id'], ),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_render_jobs_track_version_id'), 'render_jobs', ['track_version_id'], unique=False)
    op.create_index(op.f('ix_render_jobs_video_id'), 'render_jobs', ['video_id'], unique=False)

    # outbox_events
    op.create_table('outbox_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('aggregate_type', sa.String(length=64), nullable=False),
        sa.Column('aggregate_id', sa.String(length=36), nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('attempt', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('dispatched_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_outbox_events_aggregate_id'), 'outbox_events', ['aggregate_id'], unique=False)

    # audit_events
    op.create_table('audit_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=True),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('resource_type', sa.String(length=64), nullable=False),
        sa.Column('resource_id', sa.String(length=36), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_events_user_id'), 'audit_events', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_audit_events_user_id'), table_name='audit_events')
    op.drop_table('audit_events')
    op.drop_index(op.f('ix_outbox_events_aggregate_id'), table_name='outbox_events')
    op.drop_table('outbox_events')
    op.drop_index(op.f('ix_render_jobs_video_id'), table_name='render_jobs')
    op.drop_index(op.f('ix_render_jobs_track_version_id'), table_name='render_jobs')
    op.drop_table('render_jobs')
    op.drop_index(op.f('ix_analysis_runs_video_id'), table_name='analysis_runs')
    op.drop_table('analysis_runs')
    op.drop_index(op.f('ix_track_versions_video_id'), table_name='track_versions')
    op.drop_table('track_versions')
    op.drop_index(op.f('ix_annotations_frame_index'), table_name='annotations')
    op.drop_index(op.f('ix_annotations_annotation_set_id'), table_name='annotations')
    op.drop_table('annotations')
    op.drop_index(op.f('ix_annotation_sets_video_id'), table_name='annotation_sets')
    op.drop_table('annotation_sets')
    op.drop_index(op.f('ix_jobs_idempotency_key'), table_name='jobs')
    op.drop_table('jobs')
    op.drop_index(op.f('ix_upload_sessions_project_id'), table_name='upload_sessions')
    op.drop_index(op.f('ix_upload_sessions_idempotency_key'), table_name='upload_sessions')
    op.drop_table('upload_sessions')
    op.drop_index(op.f('ix_frame_manifests_video_id'), table_name='frame_manifests')
    op.drop_table('frame_manifests')
    op.drop_index(op.f('ix_videos_project_id'), table_name='videos')
    op.drop_index(op.f('ix_videos_owner_id'), table_name='videos')
    op.drop_table('videos')
    op.drop_index(op.f('ix_projects_owner_id'), table_name='projects')
    op.drop_table('projects')
    op.drop_table('users')
