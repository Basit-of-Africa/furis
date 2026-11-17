"""Research Desk password sign-in, desk team accounts, and the public read-only view."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from furis.config import ConfigError, Settings, get_settings, validate_auth_settings
from furis.db import get_db
from furis.main import app
from furis.models import (
    AttributionStatus,
    Faculty,
    IdentifierType,
    IdentityMatch,
    InstitutionalAttribution,
    MatchConfidence,
    MatchStatus,
    Publication,
    Researcher,
    ResearcherIdentifier,
    User,
    UserRole,
)
from furis.passwords import hash_password

BOOT_EMAIL, BOOT_PW = "desk@fuo.edu.ng", "Bootstrap-Pass-2026"
SECRET = "s" * 40


def cfg(**kw):
    base = dict(database_url="sqlite://", auth_mode="password", session_secret=SECRET,
                bootstrap_admin_email=BOOT_EMAIL, bootstrap_admin_password=BOOT_PW)
    return Settings(**(base | kw))


@pytest.fixture
def api(Session):
    state = {"settings": cfg()}

    def _db():
        with Session() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_settings] = lambda: state["settings"]
    yield TestClient(app), state
    app.dependency_overrides.clear()


def login(c, email, pw):
    return c.post("/auth/password/session", json={"email": email, "password": pw})


def bearer(tok):
    return {"Authorization": f"Bearer {tok}"}


# -- sign-in -------------------------------------------------------------------


def test_bootstrap_then_forced_change(api, db):
    c, _ = api
    assert login(c, BOOT_EMAIL, "wrong-password-123").status_code == 401
    r = login(c, "DESK@fuo.edu.ng", BOOT_PW)
    assert r.status_code == 200 and r.json()["user"]["must_change_password"] is True
    assert r.json()["user"]["role"] == "super_admin"
    tok = r.json()["token"]
    # Nothing but /me and the password change until the password is replaced.
    assert c.get("/me", headers=bearer(tok)).status_code == 200
    assert c.get("/researchers", headers=bearer(tok)).status_code == 403

    bad = c.post("/auth/password/change", headers=bearer(tok), json={"current_password": BOOT_PW, "new_password": "short"})
    assert bad.status_code == 400 and "12" in bad.json()["detail"]
    ok = c.post("/auth/password/change", headers=bearer(tok),
                json={"current_password": BOOT_PW, "new_password": "A much better passphrase"})
    assert ok.status_code == 200
    new_tok = ok.json()["token"]
    assert c.get("/researchers", headers=bearer(new_tok)).status_code == 200
    # The bootstrap password no longer works once the account has its own password.
    assert login(c, BOOT_EMAIL, BOOT_PW).status_code == 401
    assert login(c, BOOT_EMAIL, "A much better passphrase").status_code == 200
    stored = db.scalar(select(User).where(User.email == BOOT_EMAIL)).password_hash
    assert stored.startswith("scrypt$") and "passphrase" not in stored


def test_password_change_ends_older_sessions(api, db):
    c, _ = api
    db.add(User(email="o@fuo.edu.ng", full_name="O", role=UserRole.RESEARCH_OFFICE,
                password_hash=hash_password("Original passphrase 1")))
    db.commit()
    old = login(c, "o@fuo.edu.ng", "Original passphrase 1").json()["token"]
    import time
    time.sleep(1.1)  # session times have one-second resolution
    new = c.post("/auth/password/change", headers=bearer(old),
                 json={"current_password": "Original passphrase 1", "new_password": "Replacement passphrase 2"}).json()["token"]
    assert c.get("/me", headers=bearer(old)).status_code == 401
    assert c.get("/me", headers=bearer(new)).status_code == 200


def test_lockout_and_uniform_errors(api, db):
    c, _ = api
    db.add(User(email="o@fuo.edu.ng", full_name="O", role=UserRole.RESEARCH_OFFICE,
                password_hash=hash_password("Correct passphrase 1")))
    db.commit()
    unknown = login(c, "nobody@fuo.edu.ng", "whatever-password")
    wrong = login(c, "o@fuo.edu.ng", "whatever-password")
    assert unknown.status_code == wrong.status_code == 401 and unknown.json() == wrong.json()
    for _ in range(4):
        login(c, "o@fuo.edu.ng", "nope-nope-nope")
    locked = login(c, "o@fuo.edu.ng", "Correct passphrase 1")
    assert locked.status_code == 429 and "Try again in" in locked.json()["detail"]


def test_other_sign_in_paths_closed_in_password_mode(api, db):
    c, _ = api
    db.add(User(email="o@fuo.edu.ng", full_name="O", role=UserRole.RESEARCH_OFFICE))
    db.commit()
    assert c.get("/me", headers={"X-User-Email": "o@fuo.edu.ng"}).status_code == 401
    assert c.post("/auth/dev/session", json={"email": "o@fuo.edu.ng"}).status_code == 404
    assert c.get("/auth/config").json() == {"mode": "password"}


# -- desk team -----------------------------------------------------------------


def _admin_token(c, db):
    db.add(User(email="admin@fuo.edu.ng", full_name="Admin", role=UserRole.SUPER_ADMIN,
                password_hash=hash_password("Admin passphrase 99")))
    db.commit()
    return login(c, "admin@fuo.edu.ng", "Admin passphrase 99").json()["token"]


def test_team_accounts(api, db):
    c, _ = api
    tok = _admin_token(c, db)
    r = c.post("/users", headers=bearer(tok), json={"email": "Officer2@fuo.edu.ng", "full_name": "Officer Two"})
    assert r.status_code == 201
    temp = r.json()["temporary_password"]
    assert len(temp) >= 16 and r.json()["user"]["role"] == "research_office"
    assert c.post("/users", headers=bearer(tok), json={"email": "officer2@fuo.edu.ng", "full_name": "Dup"}).status_code == 409
    assert c.post("/users", headers=bearer(tok),
                  json={"email": "r@fuo.edu.ng", "full_name": "R", "role": "researcher"}).status_code == 422

    s2 = login(c, "officer2@fuo.edu.ng", temp).json()
    assert s2["user"]["must_change_password"] is True
    # Officers cannot manage the team.
    assert c.get("/users", headers=bearer(s2["token"])).status_code == 403

    uid = r.json()["user"]["id"]
    reset = c.post(f"/users/{uid}/reset-password", headers=bearer(tok)).json()["temporary_password"]
    assert reset != temp and login(c, "officer2@fuo.edu.ng", temp).status_code == 401
    assert c.patch(f"/users/{uid}", headers=bearer(tok), json={"is_active": False}).json()["is_active"] is False
    assert login(c, "officer2@fuo.edu.ng", reset).status_code == 401
    me = c.get("/me", headers=bearer(tok)).json()["id"]
    assert c.patch(f"/users/{me}", headers=bearer(tok), json={"is_active": False}).status_code == 409


# -- config --------------------------------------------------------------------


def test_password_mode_config(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    validate_auth_settings(cfg())  # allowed on Vercel
    with pytest.raises(ConfigError):
        validate_auth_settings(cfg(session_secret=None))
    with pytest.raises(ConfigError):
        validate_auth_settings(cfg(bootstrap_admin_password="short"))
    with pytest.raises(ConfigError):
        validate_auth_settings(cfg(bootstrap_admin_password=None))
    validate_auth_settings(cfg(bootstrap_admin_email=None, bootstrap_admin_password=None))


# -- public view ---------------------------------------------------------------


@pytest.fixture
def world(db):
    f = Faculty(name="Natural and Applied Sciences")
    db.add(f)
    db.flush()
    a = Researcher(first_name="Abdul", middle_name="Basit", last_name="Ajibade", faculty_id=f.id,
                   staff_number="FU0001", email="abdul@fuo.edu.ng")
    b = Researcher(first_name="Aisha", last_name="Lawal", faculty_id=f.id)
    db.add_all([a, b])
    db.flush()
    a.identifiers.append(ResearcherIdentifier(identifier_type=IdentifierType.ORCID, identifier_value="0000-0002-1825-0097",
                                              verified=True))
    p1 = Publication(title="Confirmed FU paper", normalised_title="x1", doi="10.1/fu", publication_year=2025)
    p2 = Publication(title="Confirmed, before FU", normalised_title="x2", publication_year=2021)
    p3 = Publication(title="Candidate only", normalised_title="x3", publication_year=2025)
    p4 = Publication(title="Rejected match", normalised_title="x4", publication_year=2024)
    db.add_all([p1, p2, p3, p4])
    db.flush()

    def m(p, r, st):
        db.add(IdentityMatch(publication_id=p.id, researcher_id=r.id, matching_method="orcid",
                             confidence=MatchConfidence.HIGH, confidence_score=0.97,
                             evidence_summary={"sources": [{"raw_name": "secret evidence"}]}, match_status=st))
    m(p1, a, MatchStatus.CONFIRMED)
    m(p2, a, MatchStatus.CONFIRMED)
    m(p3, a, MatchStatus.CANDIDATE)
    m(p4, b, MatchStatus.REJECTED)
    db.add(InstitutionalAttribution(publication_id=p1.id, researcher_id=a.id, policy_version="draft-0", evidence={},
                                    suggested_status=AttributionStatus.POTENTIAL_FU_OUTPUT,
                                    final_status=AttributionStatus.CONFIRMED_FU_OUTPUT))
    db.add(InstitutionalAttribution(publication_id=p3.id, researcher_id=a.id, policy_version="draft-0", evidence={},
                                    suggested_status=AttributionStatus.POTENTIAL_FU_OUTPUT))
    db.commit()
    return a, b


def test_public_view_shows_only_confirmed(api, world):
    c, _ = api
    a, b = world
    s = c.get("/public/summary").json()
    assert s["fu_output"] == 1 and s["researcher_publications"] == 2 and s["researchers"] == 1
    assert s["fu_output_by_year"] == [{"year": 2025, "count": 1}]

    fu = c.get("/public/publications").json()
    assert [p["title"] for p in fu] == ["Confirmed FU paper"] and fu[0]["fu_output"] is True
    every = c.get("/public/publications", params={"scope": "all"}).json()
    assert {p["title"] for p in every} == {"Confirmed FU paper", "Confirmed, before FU"}

    people = c.get("/public/researchers").json()
    assert [p["name"] for p in people] == ["Abdul Basit Ajibade"]  # Lawal has nothing confirmed
    assert people[0]["orcid"] == "0000-0002-1825-0097" and people[0]["fu_output_count"] == 1
    assert c.get(f"/public/researchers/{b.id}").status_code == 404

    detail = c.get(f"/public/researchers/{a.id}")
    blob = detail.text
    for leaked in ("FU0001", "abdul@fuo.edu.ng", "secret evidence", "Candidate only", "Rejected match", "employment"):
        assert leaked not in blob
    assert len(detail.json()["publications"]) == 2


def test_public_view_can_be_switched_off(api, world):
    c, state = api
    state["settings"] = cfg(public_view=False)
    assert c.get("/public/summary").status_code == 404
    assert c.get("/public/researchers").status_code == 404


def test_archived_researchers_hidden(api, world, db):
    from furis.models import utcnow

    c, _ = api
    a, _ = world
    db.get(Researcher, a.id).archived_at = utcnow()
    db.commit()
    assert c.get("/public/researchers").json() == []
    assert c.get("/public/summary").json()["fu_output"] == 0
