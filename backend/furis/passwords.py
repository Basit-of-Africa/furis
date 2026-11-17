"""Password hashing and checks for Research Desk accounts (standard library scrypt)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

N, R, P, DKLEN = 2**15, 8, 1, 32
MIN_LENGTH = 12
MAX_LENGTH = 256  # bound the work an attacker can request
MAX_FAILED = 5
LOCK_MINUTES = 15


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=DKLEN, maxmem=128 * 1024 * 1024)
    return f"scrypt${N}${R}${P}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or len(password) > MAX_LENGTH:
        return False
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        want = _unb64(dk)
        got = hashlib.scrypt(password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p),
                             dklen=len(want), maxmem=128 * 1024 * 1024)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, want)


# A real hash to compare against when the account does not exist, so a wrong email and a
# wrong password take the same time (no account enumeration by timing).
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def password_problem(password: str, email: str | None = None) -> str | None:
    """Why a new password is unacceptable, or None."""
    if len(password) < MIN_LENGTH:
        return f"Use at least {MIN_LENGTH} characters."
    if len(password) > MAX_LENGTH:
        return "That password is too long."
    if email and email.split("@")[0].lower() in password.lower():
        return "Don't include your email name in the password."
    if len(set(password)) < 5:
        return "Use a less repetitive password."
    return None
