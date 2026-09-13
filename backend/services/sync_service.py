"""Offline-first sync boundary. A real provider must implement both metadata and files."""
import os
from typing import Protocol
from sqlalchemy import select, func, update
from db.models import Patient, ScreeningSession, EyeResult, Report, SyncState, AppSetting, now

DEFAULT_SETTINGS = dict(automatic=False, patient_metadata=True, reports=True, retinal_images=False)


class CloudProvider(Protocol):
    # Implementations own cloud PostgreSQL transactions, object-store uploads,
    # idempotency by entity UUID, revision conflicts and authenticated transport.
    def connect(self) -> None: ...
    def sync_entity(self, entity_type: str, entity_id: str, runtime_root, settings: dict) -> str: ...


def object_key(patient_id, session_id, eye, filename):
    from uuid import UUID
    if eye not in ('OS', 'OD') or filename not in ('original.png', 'restored.png', 'lesion_overlay.png', 'gradcam.png', 'report.pdf'):
        raise ValueError('Invalid cloud artifact key.')
    return f'patients/{UUID(str(patient_id))}/sessions/{UUID(str(session_id))}/{eye}/{filename}'


class SyncService:
    def __init__(self, repository, provider: CloudProvider | None = None):
        self.repository = repository
        self.provider = provider
        self.status = 'Not connected'
        self.message = 'Cloud provider is not configured yet.'

    @property
    def configured(self):
        return bool(self.provider and os.environ.get('CLOUD_DATABASE_URL'))

    def settings(self):
        with self.repository.sessions() as db:
            row = db.get(AppSetting, 'sync_settings')
            return {**DEFAULT_SETTINGS, **(row.value if row else {})}

    def save_settings(self, settings):
        # Save preferences offline, but never imply automatic upload is active.
        if settings['automatic'] and not self.configured:
            raise ValueError('Cloud provider is not configured yet. Automatic sync remains off.')
        with self.repository.sessions.begin() as db:
            row = db.get(AppSetting, 'sync_settings')
            if row:
                row.value = settings
            else:
                db.add(AppSetting(key='sync_settings', value=settings))
        return settings

    def overview(self, files):
        with self.repository.sessions() as db:
            counts = {name: db.scalar(select(func.count()).select_from(model)) for name, model in (
                ('patients', Patient), ('sessions', ScreeningSession), ('reports', Report))}
            pending = db.scalar(select(func.count()).select_from(SyncState).where(SyncState.sync_status.in_(['PENDING', 'FAILED', 'CONFLICT'])))
            unsynced = db.scalar(select(func.count()).select_from(SyncState).where(SyncState.sync_status != 'SYNCED'))
            last = db.scalar(select(func.max(SyncState.last_synced_at)))
            db_bytes = db.scalar(select(func.pg_database_size(func.current_database())))
        return dict(status=self.status, configured=self.configured, message=self.message,
                    settings=self.settings(), counts={**counts, **files, 'database_bytes': db_bytes},
                    pending_items=pending, unsynced_items=unsynced, last_synced_at=last.isoformat() if last else None)

    def connect(self):
        if not self.configured:
            self.status, self.message = 'Not connected', 'Cloud provider is not configured yet.'
            return {'status': self.status, 'message': self.message, 'configured': False}
        self.status = 'Connecting'
        try:
            self.provider.connect()
            self.status, self.message = 'Connected', 'Cloud connection established.'
        except ConnectionError:
            self.status, self.message = 'Offline', 'Cloud is unreachable. Local screening remains available.'
        except Exception:
            self.status, self.message = 'Sync failed', 'Cloud connection failed. Local screening remains available.'
        return {'status': self.status, 'message': self.message, 'configured': self.configured}

    def sync_now(self):
        if not self.configured:
            return self.connect()
        settings = self.settings()
        allowed = []
        if settings['patient_metadata']:
            allowed += ['patient', 'session', 'eye_result']
        if settings['reports']:
            allowed += ['report']
        self.status = 'Syncing'
        with self.repository.sessions() as db:
            rows = list(db.scalars(select(SyncState).where(SyncState.entity_type.in_(allowed), SyncState.sync_status.in_(['LOCAL_ONLY', 'PENDING', 'FAILED']))))
        failed = False
        for row in rows:
            try:
                remote_id = self.provider.sync_entity(row.entity_type, str(row.entity_id), self.repository.runtime_root, settings)
                if not remote_id:
                    raise ValueError('Provider did not acknowledge the record.')
                values = dict(sync_status='SYNCED', remote_id=str(remote_id), last_synced_at=now())
            except Exception:
                values = dict(sync_status='FAILED')
                failed = True
            with self.repository.sessions.begin() as db:
                # An edit made during upload must stay pending for another pass.
                db.execute(update(SyncState).where(SyncState.id == row.id, SyncState.updated_at == row.updated_at).values(**values))
        self.status = 'Sync failed' if failed else 'Sync complete'
        self.message = 'Some items could not be synchronized. Local data was retained.' if failed else 'Selected pending records synchronized.'
        return {'status': self.status, 'message': self.message, 'configured': True}
