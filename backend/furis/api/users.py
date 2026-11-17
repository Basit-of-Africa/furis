"""Research Desk team accounts. Managed by Super Administrators.

New accounts and resets get a one-time temporary password, shown once to the
administrator who passes it on; the person must replace it at first sign-in.
"""

from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from furis.api.deps import audit, require
from furis.config import Settings, get_settings
from furis.db import get_db
from furis.models import User, UserRole, utcnow
from furis.passwords import hash_password

router = APIRouter(prefix="/users", tags=["desk team"])
require_super = require(UserRole.SUPER_ADMIN)
DESK_ROLES = {UserRole.SUPER_ADMIN, UserRole.RESEARCH_OFFICE}


class DeskUserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    must_change_password: bool
    locked: bool


class DeskUserIn(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole = UserRole.RESEARCH_OFFICE


class DeskUserPatch(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: UserRole | None = None
    is_active: bool | None = None


class TemporaryPassword(BaseModel):
    user: DeskUserOut
    temporary_password: str | None  # shown once; None in single sign-on mode


def _out(u: User) -> DeskUserOut:
    locked = u.locked_until
    if locked is not None and locked.tzinfo is None:
        locked = locked.replace(tzinfo=utcnow().tzinfo)
    return DeskUserOut(id=u.id, email=u.email, full_name=u.full_name, role=u.role, is_active=u.is_active,
                       must_change_password=bool(u.must_change_password),
                       locked=bool(locked and locked > utcnow()))


def _temporary(u: User, settings: Settings) -> str | None:
    if settings.auth_mode != "password":
        return None
    pw = secrets.token_urlsafe(12)  # 16 characters
    u.password_hash, u.must_change_password = hash_password(pw), True
    u.failed_logins, u.locked_until, u.password_changed_at = 0, None, utcnow()
    return pw


@router.get("", response_model=list[DeskUserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_super)):
    return [_out(u) for u in db.scalars(select(User).where(User.role.in_(DESK_ROLES)).order_by(User.full_name))]


@router.post("", response_model=TemporaryPassword, status_code=201)
def create_user(body: DeskUserIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
                admin: User = Depends(require_super)):
    if body.role not in DESK_ROLES:
        raise HTTPException(422, "Research Desk accounts are Super Administrator or Research Desk officer.")
    u = User(email=body.email.strip().lower(), full_name=body.full_name.strip(), role=body.role)
    db.add(u)
    pw = _temporary(u, settings)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with that email already exists.")
    audit(db, admin, "create", "user", u.id, new={"email": u.email, "role": u.role.value})
    db.commit()
    return TemporaryPassword(user=_out(u), temporary_password=pw)


@router.post("/{user_id}/reset-password", response_model=TemporaryPassword)
def reset_password(user_id: uuid.UUID, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
                   admin: User = Depends(require_super)):
    u = db.get(User, user_id)
    if not u or u.role not in DESK_ROLES:
        raise HTTPException(404)
    if settings.auth_mode != "password":
        raise HTTPException(409, "Passwords are managed by single sign-on.")
    pw = _temporary(u, settings)
    audit(db, admin, "reset_password", "user", u.id)
    db.commit()
    return TemporaryPassword(user=_out(u), temporary_password=pw)


@router.patch("/{user_id}", response_model=DeskUserOut)
def update_user(user_id: uuid.UUID, body: DeskUserPatch, db: Session = Depends(get_db),
                admin: User = Depends(require_super)):
    u = db.get(User, user_id)
    if not u or u.role not in DESK_ROLES:
        raise HTTPException(404)
    changes = body.model_dump(exclude_unset=True)
    if u.id == admin.id and (changes.get("is_active") is False or
                             ("role" in changes and changes["role"] != UserRole.SUPER_ADMIN)):
        raise HTTPException(status.HTTP_409_CONFLICT, "You can't deactivate or demote your own account.")
    if "role" in changes and changes["role"] not in DESK_ROLES:
        raise HTTPException(422, "Not a Research Desk role.")
    prev = {"full_name": u.full_name, "role": u.role.value, "is_active": u.is_active}
    for k, v in changes.items():
        setattr(u, k, v)
    audit(db, admin, "update", "user", u.id, previous=prev,
          new={k: (v.value if hasattr(v, "value") else v) for k, v in changes.items()})
    db.commit()
    return _out(u)
