import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import Session, sessionmaker

from furis.config import get_settings


def make_engine(url: str | None = None):
    url = url or get_settings().database_url
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
