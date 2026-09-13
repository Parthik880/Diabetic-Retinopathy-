"""Controlled file inventory and compensating filesystem/DB cleanup transaction."""
from pathlib import Path
import json
from uuid import uuid4
from sqlalchemy import delete, select, func
from db.models import Patient, EyeResult, Report, SyncState
from db.repository import mark_pending


class StorageService:
    def __init__(self, repository):
        self.repository = repository
        self.root = repository.runtime_root

    def inventory(self):
        result = []
        # Never enumerate PostgreSQL data files or arbitrary exported directories.
        for directory in ('runs', 'reports', 'exports', 'tmp', 'temp'):
            folder = self.root / directory
            if not folder.is_dir() or folder.is_symlink() or folder.is_junction():
                continue
            for path in folder.rglob('*'):
                if not path.is_file() or path.is_symlink():
                    continue
                resolved = path.resolve()
                if not resolved.is_relative_to(self.root):
                    continue
                parents = list(path.relative_to(self.root).parents)[:-1]
                if any((self.root / parent).is_junction() for parent in parents):
                    continue
                category = 'temporary' if directory in ('tmp', 'temp') else 'reports' if path.suffix.lower() == '.pdf' else 'images' if path.name.lower() in ('input.png', 'original.png', 'original_fundus.jpg', 'restored.png', 'restored_fundus.png') else 'artifacts'
                result.append((path, category, path.stat().st_size))
        return result

    def counts(self):
        files = self.inventory()
        return dict(images=sum(path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.tif', '.tiff') for path, _, _ in files),
                    file_bytes=sum(size for _, _, size in files), files=len(files))

    def preview(self, categories):
        files = [(p, size) for p, category, size in self.inventory() if category in categories]
        with self.repository.sessions() as db:
            unsynced = db.scalar(select(func.count()).select_from(SyncState).where(SyncState.sync_status != 'SYNCED'))
        return dict(file_count=len(files), bytes=sum(size for _, size in files), unsynced_items=unsynced,
                    deletes_history='history' in categories,
                    warning='Some selected records have not been synchronized and may be permanently lost. Legacy JSON backups and exports outside the app data folder are not removed. Cloud records are never deleted.')

    def clear(self, request):
        if not request.acknowledged:
            raise ValueError('Acknowledge the risk of losing unsynchronized data.')
        if 'history' in request.categories and request.confirmation != 'DELETE':
            raise ValueError('Type DELETE to remove patient and session history.')
        selected = [(p, category) for p, category, _ in self.inventory() if category in request.categories]
        quarantine = self.root / '.cleanup' / str(uuid4())
        quarantine.mkdir(parents=True)
        moved = []
        committed = False
        try:
            with self.repository.sessions.begin() as db:
                for path, _ in selected:
                    relative = path.relative_to(self.root)
                    target = quarantine / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    path.replace(target)
                    moved.append((path, target))
                # Journal permits manual recovery after an unexpected process/OS failure.
                (quarantine / 'journal.json').write_text(json.dumps([str(p.relative_to(self.root)) for p, _ in moved]), encoding='utf-8')
                if 'history' in request.categories:
                    db.execute(delete(SyncState).where(SyncState.entity_type.in_(['patient', 'session', 'eye_result', 'report'])))
                    db.execute(delete(Patient))  # FK cascades sessions -> eyes/reports, in one transaction.
                else:
                    removed = {str(p.relative_to(self.root)).replace('\\', '/') for p, _ in moved}
                    for report in db.scalars(select(Report)):
                        if report.report_path in removed:
                            report.report_path = None  # Preserve remote ID/key and sync state for future restore.
                            state = db.scalar(select(SyncState).where(SyncState.entity_id == report.id, SyncState.entity_type == 'report'))
                            if not state or state.sync_status != 'SYNCED':
                                mark_pending(db, 'report', report.id)
                    for eye in db.scalars(select(EyeResult)):
                        for column in ('original_image_path', 'restored_image_path', 'lesion_overlay_path', 'gradcam_path'):
                            if getattr(eye, column) in removed:
                                setattr(eye, column, None)
                                state = db.scalar(select(SyncState).where(SyncState.entity_id == eye.id, SyncState.entity_type == 'eye_result'))
                                if not state or state.sync_status != 'SYNCED':
                                    mark_pending(db, 'eye_result', eye.id)
            committed = True
        except Exception:
            if not committed:
                for original, staged in reversed(moved):
                    if staged.exists():
                        staged.replace(original)
            raise
        # Marker failure after COMMIT must never trigger a fictitious DB rollback.
        try:
            (quarantine / 'committed').touch()
        except OSError:
            return dict(deleted_files=0, history_deleted='history' in request.categories,
                        retained_files=len(moved), recovery_path=str(quarantine),
                        message='Database cleanup committed. Staged files remain in the recovery folder.')
        retained = 0
        for _, staged in moved:
            try:
                staged.unlink()
            except OSError:
                retained += 1
        return dict(deleted_files=len(moved) - retained, history_deleted='history' in request.categories,
                    retained_files=retained, recovery_path=str(quarantine) if retained else None,
                    message='Local cleanup completed. Cloud data was not changed.' if not retained else 'Database cleanup committed; some files remain in the recovery folder.')
