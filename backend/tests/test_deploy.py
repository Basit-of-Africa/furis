"""Serverless deployment: discovery queue, Vercel entry point, database settings."""

import pathlib

from sqlalchemy import select
from sqlalchemy.pool import NullPool

from furis.config import Settings, discovery_mode
from furis.db import make_engine
from furis.discovery.queue import process_pending
from furis.models import DiscoveryRequest, RequestStatus, Researcher, User, UserRole, utcnow


def test_discovery_mode_defaults(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    assert discovery_mode(Settings(database_url="sqlite://")) == "background"
    monkeypatch.setenv("VERCEL", "1")
    assert discovery_mode(Settings(database_url="sqlite://")) == "queue"
    assert discovery_mode(Settings(database_url="sqlite://", discovery_mode="background")) == "background"


def test_engine_settings(monkeypatch):
    url = "postgresql://u:p@ep-x-pooler.neon.tech/furis_db?sslmode=require&channel_binding=require"
    monkeypatch.delenv("VERCEL", raising=False)
    e = make_engine(url)
    assert e.dialect.driver == "psycopg" and not isinstance(e.pool, NullPool)
    monkeypatch.setenv("VERCEL", "1")
    assert isinstance(make_engine(url).pool, NullPool)


def test_vercel_entrypoint_is_importable():
    import importlib
    import tomllib

    cfg = tomllib.loads((pathlib.Path(__file__).parent.parent / "pyproject.toml").read_text())
    module, _, attr = cfg["tool"]["vercel"]["entrypoint"].partition(":")
    assert getattr(importlib.import_module(module), attr).title == "FURIS API"


class FakeEngine:
    def __init__(self, fail_for=()):
        self.ran, self.fail_for = [], set(fail_for)

    def run_for_researcher(self, rid):
        if rid in self.fail_for:
            raise RuntimeError("source outage")
        self.ran.append(rid)


def test_process_pending(db):
    a, b, c = (Researcher(first_name=n, last_name="X") for n in "ABC")
    db.add_all([a, b, c])
    db.flush()
    stale = DiscoveryRequest(researcher_id=c.id, status=RequestStatus.RUNNING, started_at=utcnow().replace(year=2000))
    db.add_all([DiscoveryRequest(researcher_id=a.id), DiscoveryRequest(researcher_id=b.id), stale])
    db.commit()
    eng = FakeEngine(fail_for={b.id})
    out = process_pending(db, eng)
    assert out == {"processed": 3, "done": 2, "failed": 1}
    assert set(eng.ran) == {a.id, c.id}  # stale 'running' request was retried
    statuses = {r.researcher_id: r.status for r in db.scalars(select(DiscoveryRequest))}
    assert statuses[b.id] == RequestStatus.FAILED and statuses[a.id] == RequestStatus.DONE
    assert process_pending(db, eng)["processed"] == 0


def test_queue_mode_endpoint(Session, db, monkeypatch):
    from fastapi.testclient import TestClient

    from furis.config import get_settings
    from furis.db import get_db
    from furis.main import app

    r = Researcher(first_name="A", last_name="B")
    db.add_all([r, User(email="ro@fuo.test", full_name="RO", role=UserRole.RESEARCH_OFFICE)])
    db.commit()

    def _db():
        with Session() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_settings] = lambda: Settings(database_url="sqlite://", discovery_mode="queue")
    try:
        c = TestClient(app)
        h = {"X-User-Email": "ro@fuo.test"}
        for _ in range(2):  # a second click does not queue a duplicate
            res = c.post(f"/discovery/researchers/{r.id}", headers=h)
            assert res.status_code == 202 and res.json()["status"] == "queued" and "within the hour" in res.json()["message"]
        assert len(db.scalars(select(DiscoveryRequest)).all()) == 1
        assert c.get("/discovery/requests/pending", params={"researcher_id": str(r.id)}, headers=h).json()["pending"]
    finally:
        app.dependency_overrides.clear()


def test_all_queries_failing_marks_request_failed(db):
    from furis.discovery.engine import RunSummary

    class OutageEngine:
        def run_for_researcher(self, rid):
            return RunSummary(batch_id=rid, queries=4, failed=4, new_publications=0, matches=0)

    r = Researcher(first_name="A", last_name="B")
    db.add(r)
    db.flush()
    db.add(DiscoveryRequest(researcher_id=r.id))
    db.commit()
    assert process_pending(db, OutageEngine()) == {"processed": 1, "done": 0, "failed": 1}


def test_dev_sign_in_refused_on_vercel(monkeypatch):
    import pytest

    from furis.config import ConfigError, validate_auth_settings

    monkeypatch.setenv("VERCEL", "1")
    with pytest.raises(ConfigError):
        validate_auth_settings(Settings(database_url="sqlite://"))  # environment left at default
