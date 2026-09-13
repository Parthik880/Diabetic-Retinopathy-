"""Initial relational patient, screening, report and sync metadata."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = '0001_local_storage'
down_revision = None
branch_labels = None
depends_on = None


def timestamps():
    return [sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False)]


def upgrade():
    op.create_table('patients',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('legacy_id', sa.String(200), unique=True),
        sa.Column('patient_code', sa.String(100), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('age', sa.Integer, nullable=False),
        sa.Column('gender', sa.String(20), nullable=False),
        sa.Column('phone', sa.String(20)), sa.Column('email', sa.String(254)),
        sa.Column('clinical_metadata', pg.JSONB, nullable=False), *timestamps(),
        sa.CheckConstraint('age >= 0 AND age <= 130', name='patient_age_range'))
    op.create_index('ix_patients_patient_code', 'patients', ['patient_code'], unique=True)
    op.create_table('screening_sessions',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('legacy_id', sa.String(200), unique=True),
        sa.Column('patient_id', pg.UUID(as_uuid=True), sa.ForeignKey('patients.id', ondelete='CASCADE'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('status', sa.String(30), nullable=False), sa.Column('notes', sa.Text, nullable=False), *timestamps())
    op.create_index('ix_screening_sessions_patient_id', 'screening_sessions', ['patient_id'])
    op.create_table('eye_results',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', pg.UUID(as_uuid=True), sa.ForeignKey('screening_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('eye', sa.String(2), nullable=False), sa.Column('run_id', sa.String(200)),
        sa.Column('scan_datetime', sa.DateTime(timezone=True)), sa.Column('status', sa.String(30), nullable=False),
        sa.Column('image_quality', sa.String(30)), sa.Column('dr_grade', sa.Integer),
        sa.Column('grade_label', sa.String(200)), sa.Column('confidence', sa.Float),
        sa.Column('result_json', pg.JSONB), sa.Column('original_image_path', sa.Text),
        sa.Column('restored_image_path', sa.Text), sa.Column('lesion_overlay_path', sa.Text),
        sa.Column('gradcam_path', sa.Text), sa.Column('cloud_object_keys', pg.JSONB, nullable=False), *timestamps(),
        sa.UniqueConstraint('session_id', 'eye', name='one_result_per_eye'),
        sa.CheckConstraint("eye IN ('OS', 'OD')", name='valid_eye'))
    for column in ('session_id', 'run_id', 'scan_datetime'):
        op.create_index('ix_eye_results_' + column, 'eye_results', [column])
    op.create_table('reports',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', pg.UUID(as_uuid=True), sa.ForeignKey('screening_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('eye_result_id', pg.UUID(as_uuid=True), sa.ForeignKey('eye_results.id', ondelete='CASCADE')),
        sa.Column('report_path', sa.Text), sa.Column('report_type', sa.String(30), nullable=False),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False), sa.Column('checksum_sha256', sa.String(64)),
        sa.Column('cloud_object_key', sa.Text), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('session_id', 'report_path', name='unique_session_report_path'))
    for column in ('session_id', 'eye_result_id'):
        op.create_index('ix_reports_' + column, 'reports', [column])
    op.create_table('sync_state',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('entity_type', sa.String(30), nullable=False), sa.Column('entity_id', pg.UUID(as_uuid=True), nullable=False),
        sa.Column('sync_status', sa.String(20), nullable=False), sa.Column('last_synced_at', sa.DateTime(timezone=True)),
        sa.Column('remote_id', sa.String(200)), sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('entity_type', 'entity_id', name='unique_sync_entity'),
        sa.CheckConstraint("sync_status IN ('LOCAL_ONLY','PENDING','SYNCED','FAILED','CONFLICT')", name='valid_sync_status'))
    op.create_index('ix_sync_state_sync_status', 'sync_state', ['sync_status'])
    op.create_table('app_settings', sa.Column('key', sa.String(100), primary_key=True), sa.Column('value', pg.JSONB, nullable=False))
    op.create_table('legacy_imports', sa.Column('source', sa.Text, primary_key=True),
        sa.Column('checksum_sha256', sa.String(64), nullable=False), sa.Column('imported_at', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    for table in ('legacy_imports', 'app_settings', 'sync_state', 'reports', 'eye_results', 'screening_sessions', 'patients'):
        op.drop_table(table)
