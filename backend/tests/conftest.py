import os

os.environ.setdefault("FURIS_DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from furis.config import Settings
from furis.models import Base


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def Session(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def db(Session):
    with Session() as s:
        yield s


@pytest.fixture
def settings():
    return Settings(database_url="sqlite://", fu_openalex_institution_ids=["I999FU"])
