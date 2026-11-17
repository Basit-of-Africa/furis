"""Sign-in endpoints. These are the only unauthenticated endpoints besides /health."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from furis.api.deps import audit
from furis.auth import AuthError, get_verifier, issue_session
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
              faculty_id=u.faculty_id, researcher_id=u.researcher_id)


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
