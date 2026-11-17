"""Authentication: OIDC ID-token verification and FURIS session tokens.

Flow (auth_mode="oidc"):
  1. The portal runs the authorization-code flow (with PKCE) against the university's
     OpenID Connect provider and receives an ID token.
  2. It posts the ID token and the nonce it generated to POST /auth/oidc/session.
  3. This module verifies the token's signature against the provider's published
     keys (JWKS), its issuer, audience, expiry and nonce, and the email domain.
  4. The email must belong to an existing, active FURIS user (no self-registration:
     administrators create accounts and assign roles).
  5. FURIS returns its own short-lived session token (HS256), which the portal sends
     as `Authorization: Bearer` on every API call.

The API is the only authority on identity; the portal never decides who a user is.
Deactivating a user (users.is_active = false) blocks their existing sessions at once,
because every request reloads the user.
"""

from __future__ import annotations

import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
import jwt

from furis.config import Settings

SESSION_ISSUER = "furis"
SESSION_AUDIENCE = "furis-api"
ASYMMETRIC_ALGS = ["RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512"]
CLOCK_SKEW_SECONDS = 60

# Development fallback: a per-process random secret, so dev sessions end on restart.
_DEV_SECRET = secrets.token_urlsafe(48)


class AuthError(Exception):
    """Authentication failed. `public` is safe to show the user; details go to logs."""

    def __init__(self, public: str, detail: str | None = None):
        super().__init__(detail or public)
        self.public = public


# ---------------------------------------------------------------------------
# FURIS session tokens
# ---------------------------------------------------------------------------


def _secret(settings: Settings) -> str:
    return settings.session_secret or _DEV_SECRET


def issue_session(settings: Settings, user_id: uuid.UUID, method: str) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.session_ttl_minutes)
    token = jwt.encode(
        {"iss": SESSION_ISSUER, "aud": SESSION_AUDIENCE, "sub": str(user_id), "iat": now, "exp": exp,
         "amr": method, "jti": secrets.token_urlsafe(12)},
        _secret(settings),
        algorithm="HS256",
    )
    return token, exp


def read_session(settings: Settings, token: str) -> uuid.UUID:
    try:
        claims = jwt.decode(token, _secret(settings), algorithms=["HS256"], audience=SESSION_AUDIENCE,
                            issuer=SESSION_ISSUER, leeway=CLOCK_SKEW_SECONDS,
                            options={"require": ["exp", "iat", "sub", "iss", "aud"]})
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError) as e:
        raise AuthError("Your session has expired. Please sign in again.", str(e)) from e


# ---------------------------------------------------------------------------
# OIDC ID-token verification
# ---------------------------------------------------------------------------


@dataclass
class VerifiedIdentity:
    email: str
    subject: str
    issuer: str
    name: str | None


class OidcVerifier:
    """Verifies ID tokens from one issuer. Discovery and keys are cached; an unknown
    key ID triggers at most one key refresh per minute (handles provider key rotation)."""

    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self.s = settings
        self.http = http or httpx.Client(timeout=10.0, follow_redirects=True)
        self._lock = threading.Lock()
        self._discovery: dict | None = None
        self._discovery_at = 0.0
        self._jwks: jwt.PyJWKSet | None = None
        self._jwks_at = 0.0

    def discovery(self) -> dict:
        with self._lock:
            if self._discovery is None or time.monotonic() - self._discovery_at > 3600:
                url = self.s.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration"
                try:
                    doc = self.http.get(url).raise_for_status().json()
                except (httpx.HTTPError, ValueError) as e:
                    raise AuthError("The sign-in service is unavailable. Try again shortly.",
                                    f"discovery failed: {e}") from e
                if doc.get("issuer", "").rstrip("/") != self.s.oidc_issuer.rstrip("/"):
                    raise AuthError("Sign-in is misconfigured.", f"discovery issuer mismatch: {doc.get('issuer')}")
                self._discovery, self._discovery_at = doc, time.monotonic()
            return self._discovery

    def _keys(self, force: bool = False) -> jwt.PyJWKSet:
        jwks_uri = self.discovery()["jwks_uri"]
        with self._lock:
            stale = self._jwks is None or time.monotonic() - self._jwks_at > 3600
            may_force = force and time.monotonic() - self._jwks_at > 60
            if stale or may_force:
                try:
                    self._jwks = jwt.PyJWKSet.from_dict(self.http.get(jwks_uri).raise_for_status().json())
                except (httpx.HTTPError, ValueError, jwt.PyJWTError) as e:
                    raise AuthError("The sign-in service is unavailable. Try again shortly.",
                                    f"jwks fetch failed: {e}") from e
                self._jwks_at = time.monotonic()
            return self._jwks

    def _key_for(self, token: str) -> jwt.PyJWK:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as e:
            raise AuthError("Sign-in failed.", f"malformed id_token: {e}") from e
        if header.get("alg") not in ASYMMETRIC_ALGS:
            raise AuthError("Sign-in failed.", f"disallowed alg {header.get('alg')!r}")
        kid = header.get("kid")
        for force in (False, True):
            for k in self._keys(force=force).keys:
                if kid is None or k.key_id == kid:
                    return k
        raise AuthError("Sign-in failed.", f"no signing key for kid {kid!r}")

    def verify(self, id_token: str, nonce: str) -> VerifiedIdentity:
        key = self._key_for(id_token)
        try:
            claims = jwt.decode(
                id_token, key, algorithms=ASYMMETRIC_ALGS, audience=self.s.oidc_client_id,
                issuer=self.discovery()["issuer"], leeway=CLOCK_SKEW_SECONDS,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.ExpiredSignatureError as e:
            raise AuthError("Sign-in took too long. Please try again.", str(e)) from e
        except jwt.PyJWTError as e:
            raise AuthError("Sign-in failed.", f"id_token rejected: {e}") from e

        if not nonce or not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
            raise AuthError("Sign-in failed.", "nonce mismatch (possible replay)")
        # Multiple audiences: the authorized party must be us (OIDC Core 3.1.3.7).
        aud = claims["aud"]
        if isinstance(aud, list) and len(aud) > 1 and claims.get("azp") != self.s.oidc_client_id:
            raise AuthError("Sign-in failed.", "azp does not match client id")
        for name, expected in self.s.oidc_required_claims.items():
            if str(claims.get(name)) != expected:
                raise AuthError("This account is not part of the university's sign-in directory.",
                                f"claim {name}={claims.get(name)!r}, expected {expected!r}")
        if claims.get("email_verified") is False:
            raise AuthError("Your email address is not verified with the sign-in provider.", "email_verified=false")

        email = next((str(claims[c]).strip().lower() for c in self.s.oidc_email_claims
                      if isinstance(claims.get(c), str) and "@" in claims[c]), None)
        if not email:
            raise AuthError("Your account did not provide an email address.", f"no email in {self.s.oidc_email_claims}")
        domain = email.rsplit("@", 1)[1]
        allowed = {d.lower().lstrip("@") for d in self.s.oidc_allowed_email_domains}
        if domain not in allowed:
            raise AuthError("Use your Fountain University account to sign in.", f"domain {domain} not allowed")
        return VerifiedIdentity(email=email, subject=str(claims["sub"]), issuer=claims["iss"], name=claims.get("name"))


_verifier: OidcVerifier | None = None


def get_verifier(settings: Settings) -> OidcVerifier:
    global _verifier
    if _verifier is None or _verifier.s is not settings:
        _verifier = OidcVerifier(settings)
    return _verifier
