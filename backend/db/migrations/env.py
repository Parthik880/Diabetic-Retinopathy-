from alembic import context
from db.models import Base
from db.session import make_engine, local_database_url, verify_local_storage

if context.is_offline_mode():
    context.configure(url=local_database_url(), target_metadata=Base.metadata,
                      literal_binds=True, dialect_opts={'paramstyle': 'named'})
    with context.begin_transaction():
        context.run_migrations()
else:
    with make_engine().connect() as connection:
        verify_local_storage(connection)
        connection.commit()
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
