import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import Session, sessionmaker

from furis.config import get_settings


class DatabaseUrlError(ValueError):
    pass


def clean_database_url(raw: str) -> str:
    """Accept the forms people commonly paste from Neon's Connect dialog:
    `psql 'postgresql://…'`, `DATABASE_URL=postgresql://…`, quoted values, stray spaces.
    The URL itself is never included in error messages (it contains the password)."""
    url = raw.strip()
    if url.lower().startswith("psql "):
        url = url[5:].strip()
    if "=" in url.split("://", 1)[0]:  # KEY=value, e.g. DATABASE_URL=postgresql://…
        url = url.split("=", 1)[1].strip()
    if len(url) >= 2 and url[0] == url[-1] and url[0] in "'\"":
        url = url[1:-1].strip()
    if not url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://", "sqlite:")):
        raise DatabaseUrlError(
            "The database connection string is not valid. It must start with postgresql:// "
            "(paste only the URL from Neon's Connect dialog: no 'psql', no quotes, no 'DATABASE_URL=')."
        )
    return url


def make_engine(url: str | None = None):
    url = clean_database_url(url or get_settings().database_url)
    if url.startswith("postgres://"):
        url = "postgresql://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # Neon's pooled endpoint is PgBouncer in transaction mode: don't rely on
        # server-side prepared statements surviving between transactions.
        kwargs["connect_args"] = {"prepare_threshold": None}
        if os.environ.get("VERCEL"):
            # Serverless instances freeze between requests; don't hold idle connections.
            kwargs = {"poolclass": NullPool, "connect_args": kwargs["connect_args"]}
    return create_engine(url, **kwargs)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
