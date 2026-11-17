from logging.config import fileConfig

from alembic import context

from furis.config import get_settings
from furis.db import make_engine
from furis.models import Base

if context.config.config_file_name:
    fileConfig(context.config.config_file_name)

settings = get_settings()
# Migrations use Neon's *direct* connection; pooled (PgBouncer) connections can break DDL.
URL = settings.database_url_direct or settings.database_url


def run_migrations_offline():
    context.configure(url=URL, target_metadata=Base.metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    with make_engine(URL).connect() as conn:
        context.configure(connection=conn, target_metadata=Base.metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_offline() if context.is_offline_mode() else run_migrations_online()
