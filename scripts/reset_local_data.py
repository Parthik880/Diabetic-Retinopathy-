"""Confirmed local row/file cleanup. Never remove the application-data root."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from db.session import make_engine, verify_local_storage
from db.repository import HistoryRepository
from services.storage_service import StorageService
from schemas.storage import ClearInput


def main():
    parser = argparse.ArgumentParser(description='Close RetinaGram before using this utility. Prefer Cloud Sync > Clear local data in the app.')
    parser.add_argument('--category', action='append', choices=['temporary', 'artifacts', 'reports', 'images', 'history'], required=True)
    parser.add_argument('--acknowledge-data-loss', action='store_true')
    parser.add_argument('--confirm', default='')
    args = parser.parse_args()
    app_root = Path(os.environ.get('APPDATA', Path.home() / '.local' / 'share')) / 'RetinaGram CPU'
    runtime = Path(os.environ.get('RETINA_RUNTIME_ROOT', app_root / 'runtime')).resolve()
    engine = make_engine()
    try:
        with engine.connect() as connection:
            verify_local_storage(connection)
        repository = HistoryRepository(engine, runtime, Path(os.environ.get('RETINA_HISTORY_PATH', app_root / 'retinagram-history.json')))
        result = StorageService(repository).clear(ClearInput(categories=args.category,
            acknowledged=args.acknowledge_data_loss, confirmation=args.confirm))
        print(result['message'])
        print('PostgreSQL cluster, database, tables, indexes and Alembic state were preserved.')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
