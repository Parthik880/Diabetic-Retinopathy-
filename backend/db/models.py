from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Patient(Timestamps, Base):
    __tablename__ = 'patients'
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    legacy_id = mapped_column(String(200), unique=True, nullable=True)
    patient_code = mapped_column(String(100), unique=True, nullable=False, index=True)
    name = mapped_column(String(200), nullable=False)
    age = mapped_column(Integer, nullable=False)
    gender = mapped_column(String(20), nullable=False)
    phone = mapped_column(String(20), nullable=True)
    email = mapped_column(String(254), nullable=True)
    clinical_metadata = mapped_column(JSONB, nullable=False, default=dict)
    __table_args__ = (CheckConstraint('age >= 0 AND age <= 130', name='patient_age_range'),)


class ScreeningSession(Timestamps, Base):
    __tablename__ = 'screening_sessions'
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    legacy_id = mapped_column(String(200), unique=True, nullable=True)
    patient_id = mapped_column(ForeignKey('patients.id', ondelete='CASCADE'), nullable=False, index=True)
    started_at = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at = mapped_column(DateTime(timezone=True), nullable=True)
    status = mapped_column(String(30), nullable=False, default='WAITING')
    notes = mapped_column(Text, nullable=False, default='')


class EyeResult(Timestamps, Base):
    __tablename__ = 'eye_results'
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id = mapped_column(ForeignKey('screening_sessions.id', ondelete='CASCADE'), nullable=False, index=True)
    eye = mapped_column(String(2), nullable=False)
    run_id = mapped_column(String(200), nullable=True, index=True)
    scan_datetime = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    status = mapped_column(String(30), nullable=False, default='WAITING')
    image_quality = mapped_column(String(30), nullable=True)
    dr_grade = mapped_column(Integer, nullable=True)
    grade_label = mapped_column(String(200), nullable=True)
    confidence = mapped_column(Float, nullable=True)
    result_json = mapped_column(JSONB, nullable=True)
    original_image_path = mapped_column(Text, nullable=True)
    restored_image_path = mapped_column(Text, nullable=True)
    lesion_overlay_path = mapped_column(Text, nullable=True)
    gradcam_path = mapped_column(Text, nullable=True)
    cloud_object_keys = mapped_column(JSONB, nullable=False, default=dict)
    __table_args__ = (UniqueConstraint('session_id', 'eye', name='one_result_per_eye'),
                      CheckConstraint("eye IN ('OS', 'OD')", name='valid_eye'))


class Report(Base):
    __tablename__ = 'reports'
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id = mapped_column(ForeignKey('screening_sessions.id', ondelete='CASCADE'), nullable=False, index=True)
    eye_result_id = mapped_column(ForeignKey('eye_results.id', ondelete='CASCADE'), nullable=True, index=True)
    report_path = mapped_column(Text, nullable=True)
    report_type = mapped_column(String(30), nullable=False, default='screening_pdf')
    generated_at = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    checksum_sha256 = mapped_column(String(64), nullable=True)
    cloud_object_key = mapped_column(Text, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    __table_args__ = (UniqueConstraint('session_id', 'report_path', name='unique_session_report_path'),)


class SyncState(Base):
    __tablename__ = 'sync_state'
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    entity_type = mapped_column(String(30), nullable=False)
    entity_id = mapped_column(UUID(as_uuid=True), nullable=False)
    sync_status = mapped_column(String(20), nullable=False, default='LOCAL_ONLY', index=True)
    last_synced_at = mapped_column(DateTime(timezone=True), nullable=True)
    remote_id = mapped_column(String(200), nullable=True)
    updated_at = mapped_column(DateTime(timezone=True), default=now, onupdate=now, nullable=False)
    __table_args__ = (UniqueConstraint('entity_type', 'entity_id', name='unique_sync_entity'),
                      CheckConstraint("sync_status IN ('LOCAL_ONLY','PENDING','SYNCED','FAILED','CONFLICT')", name='valid_sync_status'))


class AppSetting(Base):
    __tablename__ = 'app_settings'
    key = mapped_column(String(100), primary_key=True)
    value = mapped_column(JSONB, nullable=False)


class LegacyImport(Base):
    __tablename__ = 'legacy_imports'
    source = mapped_column(Text, primary_key=True)
    checksum_sha256 = mapped_column(String(64), nullable=False)
    imported_at = mapped_column(DateTime(timezone=True), default=now, nullable=False)
