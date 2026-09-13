import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text


def local_database_url():
    load_dotenv(Path(os.environ.get('APPDATA', Path.home() / '.local' / 'share')) / 'RetinaGram CPU' / 'backend.env', override=False)
    load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)
    url = os.environ.get('LOCAL_DATABASE_URL') or os.environ.get('DATABASE_URL')
    if not url:
        raise RuntimeError('Local patient database unavailable. Configure LOCAL_DATABASE_URL in backend/.env.')
    parsed = make_url(url)
    if parsed.drivername != 'postgresql+psycopg':
        raise RuntimeError('Local patient database requires postgresql+psycopg.')
    return url


def make_engine(url=None):
    # No SQL/parameter logging: SQLAlchemy errors can otherwise expose PHI.
    return create_engine(url or local_database_url(), pool_pre_ping=True, pool_size=3,
                         max_overflow=2, connect_args={'connect_timeout': 3}, hide_parameters=True)


def verify_local_storage(connection):
    """Verify the server's real path, never infer it from DATABASE_URL."""
    host = connection.engine.url.host
    if host not in ('localhost', '127.0.0.1', '::1'):
        raise RuntimeError('The local patient database must run on loopback.')
    data_directory = Path(connection.execute(text('SHOW data_directory')).scalar_one()).resolve()
    application_root = Path(os.environ.get('APPDATA', Path.home() / '.local' / 'share')) / 'RetinaGram CPU'
    allowed = [Path(os.environ.get('PROGRAMDATA', 'C:/ProgramData')) / 'RetinaGram' / 'postgres-data',
               application_root / 'postgres-data', application_root / 'postgres-qa']
    if data_directory not in [root.resolve() for root in allowed]:
        raise RuntimeError('PostgreSQL data directory must be inside RetinaGram-owned application data.')
    return str(data_directory)


def session_factory(engine):
    return sessionmaker(engine, expire_on_commit=False)
