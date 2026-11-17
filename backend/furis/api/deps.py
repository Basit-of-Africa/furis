"""Authentication and role-based access (§13).

Every request is identified by a FURIS session token (`Authorization: Bearer`),
issued by /auth/oidc/session after single sign-on (see furis/auth.py).
In auth_mode "dev_header" only, an `X-User-Email` header is also accepted, for
local development, tests and the CLI sandbox. It is refused in production.
"""

from __future__ import annotations

import uuid
from datetime import timezone

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from furis.auth import AuthError, read_session
from furis.config import Settings, get_settings
from furis.db import get_db
from furis.models import AuditLog, Researcher, User, UserRole

ADMIN_ROLES = {UserRole.SUPER_ADMIN, UserRole.RESEARCH_OFFICE}


def _unauthorized(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, msg, headers={"WWW-Authenticate": "Bearer"})


# Reachable while a temporary password must still be replaced.
PASSWORD_CHANGE_PATHS = {"/me", "/auth/password/change"}


def current_user(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    authorization: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
) -> User:
    issued_at = None
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise _unauthorized("expected a Bearer token")
        try:
            user_id, issued_at = read_session(settings, token.strip())
        except AuthError as e:
            raise _unauthorized(e.public) from e
        user = db.get(User, user_id)
    elif x_user_email and settings.auth_mode == "dev_header":
        user = db.scalar(select(User).where(User.email == x_user_email.lower()))
    else:
        raise _unauthorized("not signed in")
    if not user or not user.is_active:
        raise _unauthorized("account not found or deactivated")
    # Changing or resetting a password ends every session issued before it.
    changed = user.password_changed_at
    if changed is not None and changed.tzinfo is None:
        changed = changed.replace(tzinfo=timezone.utc)  # SQLite returns naive UTC values
    if issued_at is not None and changed is not None and issued_at < int(changed.timestamp()):
        raise _unauthorized("Your password was changed. Please sign in again.")
    if user.must_change_password and request.url.path not in PASSWORD_CHANGE_PATHS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Choose a new password before continuing.")
    return user


def require(*roles: UserRole):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")
        return user

    return dep


require_admin = require(UserRole.SUPER_ADMIN, UserRole.RESEARCH_OFFICE)


def can_view_researcher(user: User, r: Researcher) -> bool:
    if user.role in ADMIN_ROLES:
        return True
    if user.role == UserRole.FACULTY_ADMIN:
        return user.faculty_id is not None and user.faculty_id == r.faculty_id
    return user.researcher_id == r.id


def get_researcher_for(db: Session, user: User, researcher_id: uuid.UUID) -> Researcher:
    r = db.get(Researcher, researcher_id)
    if not r or not can_view_researcher(user, r):
        # 404 rather than 403 so record existence is not disclosed.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "researcher not found")
    return r


def audit(db: Session, user: User | None, action: str, entity_type: str, entity_id, previous=None, new=None):
    db.add(AuditLog(user_id=user.id if user else None, action=action, entity_type=entity_type,
                    entity_id=str(entity_id), previous_value=previous, new_value=new))
