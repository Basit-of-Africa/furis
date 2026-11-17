"""Authentication and role-based access (§13).

AUTH MODE "dev_header" trusts an `X-User-Email` header and exists only for local
development and the pilot sandbox. Replace `current_user` with real SSO/OIDC token
verification before FURIS holds real staff data on a reachable server.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from furis.config import get_settings
from furis.db import get_db
from furis.models import AuditLog, Researcher, User, UserRole

ADMIN_ROLES = {UserRole.SUPER_ADMIN, UserRole.RESEARCH_OFFICE}


def current_user(
    db: Session = Depends(get_db), x_user_email: str | None = Header(default=None)
) -> User:
    if get_settings().auth_mode != "dev_header":
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "configure an authentication provider")
    if not x_user_email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing X-User-Email")
    user = db.scalar(select(User).where(User.email == x_user_email.lower(), User.is_active.is_(True)))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown user")
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
