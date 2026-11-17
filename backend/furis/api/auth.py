"""Sign-in endpoints. These are the only unauthenticated endpoints besides /health."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

import hmac
from datetime import timedelta

from furis.api.deps import audit, current_user
from furis.auth import AuthError, get_verifier, issue_session
from furis.models import UserRole, utcnow
from furis.passwords import (DUMMY_HASH, LOCK_MINUTES, MAX_FAILED, MAX_LENGTH, hash_password, password_problem,
                             verify_password)
from furis.config import Settings, get_settings
from furis.db import get_db
from furis.models import User
from furis.schemas import Me

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger(__name__)


class AuthConfig(BaseModel):
    mode: str


class OidcSessionIn(BaseModel):
    id_token: str = Field(min_length=20, max_length=20000)
    nonce: str = Field(min_length=16, max_length=256)


class DevSessionIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class SessionOut(BaseModel):
    token: str
    expires_at: datetime
    user: Me


def _me(u: User) -> Me:
    return Me(id=u.id, email=u.email, full_name=u.full_name, role=u.role.value,
              faculty_id=u.faculty_id, researcher_id=u.researcher_id,
              must_change_password=bool(u.must_change_password))


def _session(db: Session, settings: Settings, user: User, method: str) -> SessionOut:
    token, exp = issue_session(settings, user.id, method)
    audit(db, user, "sign_in", "user", user.id, new={"method": method})
    db.commit()
    return SessionOut(token=token, expires_at=exp, user=_me(user))


@router.get("/config", response_model=AuthConfig)
def auth_config(settings: Settings = Depends(get_settings)):
    return AuthConfig(mode=settings.auth_mode)


@router.post("/oidc/session", response_model=SessionOut)
def oidc_session(body: OidcSessionIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    if settings.auth_mode != "oidc":
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    try:
        ident = get_verifier(settings).verify(body.id_token, body.nonce)
    except AuthError as e:
        log.warning("OIDC sign-in rejected: %s", e)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, e.public) from e
    user = db.scalar(select(User).where(User.email == ident.email))
    if not user or not user.is_active:
        # Record the attempt (domain only) so administrators can see who needs an account.
        audit(db, None, "sign_in_refused", "auth", ident.email.rsplit("@", 1)[1],
              new={"reason": "no active FURIS account"})
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "You signed in successfully, but you do not have a FURIS account yet. "
                            "Ask the Research Office to add you.")
    return _session(db, settings, user, "oidc")


@router.post("/dev/session", response_model=SessionOut)
def dev_session(body: DevSessionIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    """Development sign-in by email, with no password. Disabled outside dev_header mode."""
    if settings.auth_mode != "dev_header":
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No active FURIS account uses that email address.")
    return _session(db, settings, user, "dev")


# -- password sign-in (Research Desk) -----------------------------------------

class PasswordSessionIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=MAX_LENGTH)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=MAX_LENGTH)
    new_password: str = Field(min_length=1, max_length=MAX_LENGTH)


BAD_CREDENTIALS = "Email or password is incorrect."


def _bootstrap(db: Session, settings: Settings, email: str, password: str) -> User | None:
    """Create or arm the first officer from the bootstrap settings, once."""
    if not (settings.bootstrap_admin_email and settings.bootstrap_admin_password):
        return None
    if email != settings.bootstrap_admin_email.strip().lower():
        return None
    if not hmac.compare_digest(password.encode(), settings.bootstrap_admin_password.encode()):
        return None
    user = db.scalar(select(User).where(User.email == email))
    if user is not None and user.password_hash is not None:
        return None  # already set up: its own password applies from now on
    if user is None:
        user = User(email=email, full_name=settings.bootstrap_admin_name, role=UserRole.SUPER_ADMIN)
        db.add(user)
    user.password_hash = hash_password(password)
    user.must_change_password = True
    user.is_active = True
    db.flush()
    audit(db, user, "bootstrap_admin", "user", user.id)
    return user


@router.post("/password/session", response_model=SessionOut)
def password_session(body: PasswordSessionIn, db: Session = Depends(get_db),
                     settings: Settings = Depends(get_settings)):
    if settings.auth_mode != "password":
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    email = body.email.strip().lower()
    boot = _bootstrap(db, settings, email, body.password)
    if boot is not None:
        return _session(db, settings, boot, "password")

    user = db.scalar(select(User).where(User.email == email))
    now = utcnow()
    if user is None or not user.is_active or not user.password_hash:
        verify_password(body.password, DUMMY_HASH)  # same timing as a real check
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_CREDENTIALS)
    locked = user.locked_until
    if locked is not None and locked.tzinfo is None:
        locked = locked.replace(tzinfo=now.tzinfo)
    if locked is not None and locked > now:
        minutes = max(1, int((locked - now).total_seconds() // 60) + 1)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Too many failed attempts. Try again in {minutes} minute{'s' if minutes > 1 else ''}.")
    if not verify_password(body.password, user.password_hash):
        user.failed_logins = (user.failed_logins or 0) + 1
        if user.failed_logins >= MAX_FAILED:
            user.locked_until, user.failed_logins = now + timedelta(minutes=LOCK_MINUTES), 0
        audit(db, None, "sign_in_failed", "user", user.id)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_CREDENTIALS)
    user.failed_logins, user.locked_until = 0, None
    return _session(db, settings, user, "password")


@router.post("/password/change", response_model=SessionOut)
def change_password(body: PasswordChangeIn, db: Session = Depends(get_db),
                    settings: Settings = Depends(get_settings), user: User = Depends(current_user)):
    if settings.auth_mode != "password":
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your current password is incorrect.")
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a password different from the current one.")
    problem = password_problem(body.new_password, user.email)
    if problem:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    user.password_changed_at = utcnow()
    audit(db, user, "password_changed", "user", user.id)
    db.flush()
    return _session(db, settings, user, "password")  # a fresh session; older ones stop working
