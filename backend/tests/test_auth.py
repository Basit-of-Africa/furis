"""Single sign-on: ID-token verification, FURIS sessions, mode gating, config safety."""

import json
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from furis.auth import AuthError, OidcVerifier, issue_session, read_session
from furis.config import ConfigError, Settings, get_settings, validate_auth_settings
from furis.db import get_db
from furis.main import app
from furis.models import User, UserRole

ISSUER = "https://idp.example.test"
CLIENT = "furis-portal"
NONCE = "n" * 32


def _keypair(kid):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    return key, jwk | {"kid": kid, "use": "sig", "alg": "RS256"}


KEY, JWK = _keypair("k1")
OTHER_KEY, _ = _keypair("k1")  # same kid, different key: a forged token


class FakeIdP:
    def __init__(self):
        self.jwks = {"keys": [JWK]}
        self.jwks_calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/.well-known/openid-configuration":
            return httpx.Response(200, json={"issuer": ISSUER, "jwks_uri": f"{ISSUER}/jwks",
                                             "authorization_endpoint": f"{ISSUER}/auth", "token_endpoint": f"{ISSUER}/token"})
        if request.url.path == "/jwks":
            self.jwks_calls += 1
            return httpx.Response(200, json=self.jwks)
        return httpx.Response(404)


def settings(**kw):
    base = dict(auth_mode="oidc", oidc_issuer=ISSUER, oidc_client_id=CLIENT, oidc_allowed_email_domains=["fuo.edu.ng"],
                session_secret="s" * 40, database_url="sqlite://")
    return Settings(**(base | kw))


def token(key=KEY, kid="k1", **claims):
    now = int(time.time())
    body = {"iss": ISSUER, "aud": CLIENT, "sub": "user-123", "iat": now, "exp": now + 300, "nonce": NONCE,
            "email": "ro@fuo.edu.ng", "email_verified": True} | claims
    body = {k: v for k, v in body.items() if v is not None}
    return jwt.encode(body, key, algorithm="RS256", headers={"kid": kid})


@pytest.fixture
def idp():
    return FakeIdP()


def verifier(idp, **kw):
    return OidcVerifier(settings(**kw), http=httpx.Client(transport=httpx.MockTransport(idp.handler)))


def test_valid_token(idp):
    ident = verifier(idp).verify(token(), NONCE)
    assert ident.email == "ro@fuo.edu.ng" and ident.subject == "user-123"


def test_entra_style_email_claim(idp):
    t = token(email=None, email_verified=None, preferred_username="Abdul@FUO.edu.ng")
    assert verifier(idp).verify(t, NONCE).email == "abdul@fuo.edu.ng"


@pytest.mark.parametrize("tok,why", [
    (lambda: token(aud="someone-else"), "wrong audience"),
    (lambda: token(iss="https://evil.test"), "wrong issuer"),
    (lambda: token(exp=int(time.time()) - 600, iat=int(time.time()) - 900), "expired"),
    (lambda: token(nonce="x" * 32), "nonce mismatch / replay"),
    (lambda: token(nonce=None), "missing nonce"),
    (lambda: token(key=OTHER_KEY), "forged signature"),
    (lambda: token(email="someone@gmail.com"), "outside allowed domain"),
    (lambda: token(email_verified=False), "unverified email"),
    (lambda: token(email=None, preferred_username=None), "no email"),
    (lambda: token(aud=[CLIENT, "other"], azp="other"), "azp mismatch"),
])
def test_rejected_tokens(idp, tok, why):
    with pytest.raises(AuthError):
        verifier(idp).verify(tok(), NONCE)


def test_alg_none_and_hs256_rejected(idp):
    unsigned = jwt.encode({"iss": ISSUER, "aud": CLIENT, "sub": "x", "nonce": NONCE}, None, algorithm="none")
    with pytest.raises(AuthError):
        verifier(idp).verify(unsigned, NONCE)
    # Classic confusion attack: HS256 signed with the public key material.
    hs = jwt.encode({"iss": ISSUER, "aud": CLIENT, "sub": "x", "nonce": NONCE}, "s" * 32, algorithm="HS256",
                    headers={"kid": "k1"})
    with pytest.raises(AuthError):
        verifier(idp).verify(hs, NONCE)


def test_required_claims(idp):
    v = verifier(idp, oidc_required_claims={"tid": "fu-tenant"})
    with pytest.raises(AuthError):
        v.verify(token(), NONCE)
    assert v.verify(token(tid="fu-tenant"), NONCE).email == "ro@fuo.edu.ng"


def test_key_rotation_refetches_once(idp):
    v = verifier(idp)
    v.verify(token(), NONCE)
    new_key, new_jwk = _keypair("k2")
    idp.jwks = {"keys": [JWK, new_jwk]}
    v._jwks_at -= 120  # allow a forced refresh
    assert v.verify(token(key=new_key, kid="k2"), NONCE)
    assert idp.jwks_calls == 2
    with pytest.raises(AuthError):  # unknown kid again within a minute: no hammering
        v.verify(token(kid="k3"), NONCE)
    assert idp.jwks_calls == 2


def test_session_tokens():
    s = settings()
    import uuid
    uid = uuid.uuid4()
    tok, _ = issue_session(s, uid, "oidc")
    assert read_session(s, tok) == uid
    with pytest.raises(AuthError):
        read_session(settings(session_secret="t" * 40), tok)  # different secret
    expired = jwt.encode({"iss": "furis", "aud": "furis-api", "sub": str(uid), "iat": 0, "exp": 1}, s.session_secret,
                         algorithm="HS256")
    with pytest.raises(AuthError):
        read_session(s, expired)


@pytest.mark.parametrize("kw", [
    dict(environment="production", auth_mode="dev_header", session_secret="s" * 40),
    dict(environment="production", session_secret="short"),
    dict(oidc_issuer=None),
    dict(oidc_allowed_email_domains=[]),
    dict(session_secret=None),
    dict(auth_mode="magic"),
])
def test_unsafe_config_refused(kw):
    with pytest.raises(ConfigError):
        validate_auth_settings(settings(**kw))


def test_safe_production_config_accepted():
    validate_auth_settings(settings(environment="production"))
    validate_auth_settings(Settings(database_url="sqlite://"))  # local development default


# ---- API ---------------------------------------------------------------------


@pytest.fixture
def api(Session, db, idp, monkeypatch):
    db.add_all([User(email="ro@fuo.edu.ng", full_name="Research Office", role=UserRole.RESEARCH_OFFICE),
                User(email="gone@fuo.edu.ng", full_name="Former", role=UserRole.RESEARCHER, is_active=False)])
    db.commit()
    state = {"settings": settings()}

    def _db():
        with Session() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_settings] = lambda: state["settings"]
    import furis.api.auth as auth_router
    v = verifier(idp)
    monkeypatch.setattr(auth_router, "get_verifier", lambda s: v)
    yield TestClient(app), state
    app.dependency_overrides.clear()


def test_oidc_sign_in_flow(api):
    client, _ = api
    assert client.get("/auth/config").json() == {"mode": "oidc"}
    res = client.post("/auth/oidc/session", json={"id_token": token(), "nonce": NONCE})
    assert res.status_code == 200, res.text
    tok = res.json()["token"]
    me = client.get("/me", headers={"Authorization": f"Bearer {tok}"})
    assert me.status_code == 200 and me.json()["role"] == "research_office"


def test_oidc_refusals(api):
    client, _ = api
    assert client.post("/auth/oidc/session", json={"id_token": token(nonce="z" * 32), "nonce": NONCE}).status_code == 401
    # Valid university account but no FURIS account: authenticated, not authorised.
    r = client.post("/auth/oidc/session", json={"id_token": token(email="new@fuo.edu.ng"), "nonce": NONCE})
    assert r.status_code == 403 and "Research Office" in r.json()["detail"]
    assert client.post("/auth/oidc/session",
                       json={"id_token": token(email="gone@fuo.edu.ng"), "nonce": NONCE}).status_code == 403


def test_dev_header_and_dev_session_disabled_in_oidc_mode(api):
    client, _ = api
    assert client.get("/me", headers={"X-User-Email": "ro@fuo.edu.ng"}).status_code == 401
    assert client.post("/auth/dev/session", json={"email": "ro@fuo.edu.ng"}).status_code == 404


def test_deactivation_ends_existing_sessions(api, db):
    client, _ = api
    tok = client.post("/auth/oidc/session", json={"id_token": token(), "nonce": NONCE}).json()["token"]
    u = db.query(User).filter_by(email="ro@fuo.edu.ng").one()
    u.is_active = False
    db.commit()
    assert client.get("/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_dev_session_in_dev_mode(api):
    client, state = api
    state["settings"] = settings(auth_mode="dev_header")
    res = client.post("/auth/dev/session", json={"email": "RO@fuo.edu.ng"})
    assert res.status_code == 200
    assert client.get("/me", headers={"Authorization": f"Bearer {res.json()['token']}"}).status_code == 200
    assert client.post("/auth/oidc/session", json={"id_token": token(), "nonce": NONCE}).status_code == 404
    assert client.get("/me", headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_google_issuer_forms():
    class GoogleIdP(FakeIdP):
        def handler(self, request):
            if request.url.path == "/.well-known/openid-configuration":
                return httpx.Response(200, json={"issuer": "https://accounts.google.com", "jwks_uri": f"{ISSUER}/jwks"})
            return super().handler(request)

    g = GoogleIdP()
    v = OidcVerifier(settings(oidc_issuer="https://accounts.google.com", oidc_required_claims={"hd": "fuo.edu.ng"}),
                     http=httpx.Client(transport=httpx.MockTransport(g.handler)))
    for iss in ("https://accounts.google.com", "accounts.google.com"):
        assert v.verify(token(iss=iss, hd="fuo.edu.ng"), NONCE).email == "ro@fuo.edu.ng"
    with pytest.raises(AuthError):  # personal Gmail-style account: no hd claim
        v.verify(token(iss="accounts.google.com"), NONCE)


def test_neon_integration_env_names(monkeypatch):
    for k in ("FURIS_DATABASE_URL", "FURIS_DATABASE_URL_DIRECT"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@ep-x-pooler.neon.tech/furis_db?sslmode=require")
    monkeypatch.setenv("DATABASE_URL_UNPOOLED", "postgresql://u:p@ep-x.neon.tech/furis_db?sslmode=require")
    s = Settings(_env_file=None)
    assert "pooler" in s.database_url and "pooler" not in s.database_url_direct
    monkeypatch.setenv("FURIS_DATABASE_URL", "sqlite://")
    assert Settings(_env_file=None).database_url == "sqlite://"  # FURIS_* wins
