from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from furis import schemas as s
from furis.api.deps import audit, current_user, get_researcher_for, require_admin
from furis.config import get_settings
from furis.db import get_db
from furis.discovery.engine import ensure_system_variants
from furis.discovery.names import normalise_name
from furis.discovery.sources.base import HttpClient
from furis.discovery.sources.openalex import OpenAlexSource
from furis.models import (
    IdentityMatch,
    InstitutionalAttribution,
    Publication,
    ConfirmationStatus,
    Department,
    EmploymentHistory,
    Faculty,
    NameVariant,
    Researcher,
    ResearcherIdentifier,
    User,
    UserRole,
    VariantType,
    utcnow,
)
from furis.staff_import import import_staff_csv

router = APIRouter(tags=["registry"])


@router.get("/faculties", response_model=list[s.FacultyOut])
def list_faculties(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return db.scalars(select(Faculty).order_by(Faculty.name)).all()


@router.post("/faculties", response_model=s.FacultyOut, status_code=201)
def create_faculty(body: s.FacultyIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    f = Faculty(**body.model_dump())
    db.add(f)
    db.flush()
    audit(db, user, "create", "faculty", f.id, new=body.model_dump())
    db.commit()
    return f


@router.get("/departments", response_model=list[s.DepartmentOut])
def list_departments(faculty_id: uuid.UUID | None = None, db: Session = Depends(get_db),
                     _: User = Depends(current_user)):
    q = select(Department).order_by(Department.name)
    if faculty_id:
        q = q.where(Department.faculty_id == faculty_id)
    return db.scalars(q).all()


@router.post("/departments", response_model=s.DepartmentOut, status_code=201)
def create_department(body: s.DepartmentIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    d = Department(**body.model_dump())
    db.add(d)
    db.flush()
    audit(db, user, "create", "department", d.id, new=body.model_dump(mode="json"))
    db.commit()
    return d


@router.get("/researchers", response_model=list[s.ResearcherOut])
def list_researchers(
    faculty_id: uuid.UUID | None = None, department_id: uuid.UUID | None = None, q: str | None = None,
    limit: int = Query(100, le=500), offset: int = 0,
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    stmt = select(Researcher).where(Researcher.archived_at.is_(None)).order_by(Researcher.last_name)
    if user.role == UserRole.FACULTY_ADMIN:
        stmt = stmt.where(Researcher.faculty_id == user.faculty_id)
    elif user.role == UserRole.RESEARCHER:
        stmt = stmt.where(Researcher.id == user.researcher_id)
    if faculty_id:
        stmt = stmt.where(Researcher.faculty_id == faculty_id)
    if department_id:
        stmt = stmt.where(Researcher.department_id == department_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Researcher.last_name.ilike(like) | Researcher.first_name.ilike(like))
    return db.scalars(stmt.limit(limit).offset(offset)).all()


@router.post("/researchers", response_model=s.ResearcherDetail, status_code=201)
def create_researcher(body: s.ResearcherIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    r = Researcher(**body.model_dump())
    db.add(r)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "staff_number already exists")
    ensure_system_variants(db, r)
    audit(db, user, "create", "researcher", r.id, new=body.model_dump(mode="json"))
    db.commit()
    return r


@router.post("/researchers/import")
async def import_researchers(file: UploadFile = File(...), db: Session = Depends(get_db),
                             user: User = Depends(require_admin)):
    text = (await file.read()).decode("utf-8-sig")
    result = import_staff_csv(db, text)
    audit(db, user, "import", "researcher", "csv", new=result)
    db.commit()
    return result


@router.get("/researchers/{researcher_id}", response_model=s.ResearcherDetail)
def get_researcher(researcher_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return get_researcher_for(db, user, researcher_id)


@router.patch("/researchers/{researcher_id}", response_model=s.ResearcherDetail)
def update_researcher(researcher_id: uuid.UUID, body: s.ResearcherPatch, db: Session = Depends(get_db),
                      user: User = Depends(require_admin)):
    r = get_researcher_for(db, user, researcher_id)
    changes = body.model_dump(exclude_unset=True)
    prev = {k: str(getattr(r, k)) for k in changes}
    for k, v in changes.items():
        setattr(r, k, v)
    if {"first_name", "middle_name", "last_name"} & changes.keys():
        ensure_system_variants(db, r)
    audit(db, user, "update", "researcher", r.id, previous=prev, new={k: str(v) for k, v in changes.items()})
    db.commit()
    return r


@router.post("/researchers/{researcher_id}/identifiers", response_model=s.IdentifierOut, status_code=201)
def add_identifier(researcher_id: uuid.UUID, body: s.IdentifierIn, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    r = get_researcher_for(db, user, researcher_id)
    # Researchers may submit identifiers; only admins may mark them verified.
    verified = body.verified and user.role in (UserRole.SUPER_ADMIN, UserRole.RESEARCH_OFFICE)
    ident = ResearcherIdentifier(researcher_id=r.id, identifier_type=body.identifier_type,
                                 identifier_value=body.identifier_value, verified=verified,
                                 verified_by=user.id if verified else None, verified_at=utcnow() if verified else None)
    db.add(ident)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "identifier already registered to a researcher")
    audit(db, user, "create", "researcher_identifier", ident.id, new=body.model_dump(mode="json"))
    db.commit()
    return ident


@router.post("/identifiers/{identifier_id}/verify", response_model=s.IdentifierOut)
def verify_identifier(identifier_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    ident = db.get(ResearcherIdentifier, identifier_id)
    if not ident:
        raise HTTPException(404)
    ident.verified, ident.verified_by, ident.verified_at = True, user.id, utcnow()
    audit(db, user, "verify", "researcher_identifier", ident.id)
    db.commit()
    return ident


@router.get("/researchers/{researcher_id}/openalex-author-candidates")
def openalex_author_candidates(researcher_id: uuid.UUID, db: Session = Depends(get_db),
                               user: User = Depends(require_admin)):
    """Possible OpenAlex author profiles, for a reviewer to confirm (never auto-linked)."""
    r = get_researcher_for(db, user, researcher_id)
    settings = get_settings()
    return OpenAlexSource(HttpClient(settings), settings).search_authors(r.full_name)


@router.post("/researchers/{researcher_id}/variants", response_model=s.VariantOut, status_code=201)
def add_alias(researcher_id: uuid.UUID, body: s.VariantIn, db: Session = Depends(get_db),
              user: User = Depends(current_user)):
    """A researcher-confirmed alias (Category 2)."""
    r = get_researcher_for(db, user, researcher_id)
    n = normalise_name(body.variant_name)
    v = next((x for x in r.name_variants if x.normalised_name == n), None)
    if v is None:
        v = NameVariant(researcher_id=r.id, variant_name=body.variant_name, normalised_name=n,
                        variant_type=VariantType.RESEARCHER_CONFIRMED, source="researcher")
        db.add(v)
    v.confirmation_status = ConfirmationStatus.CONFIRMED
    if v.variant_type == VariantType.DISCOVERED:
        v.variant_type = VariantType.RESEARCHER_CONFIRMED
    db.flush()
    audit(db, user, "confirm_alias", "name_variant", v.id, new={"variant_name": body.variant_name})
    db.commit()
    return v


@router.patch("/variants/{variant_id}", response_model=s.VariantOut)
def review_variant(variant_id: uuid.UUID, body: s.VariantPatch, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    v = db.get(NameVariant, variant_id)
    if not v:
        raise HTTPException(404)
    get_researcher_for(db, user, v.researcher_id)
    prev = v.confirmation_status.value
    v.confirmation_status = body.confirmation_status
    if body.confirmation_status == ConfirmationStatus.CONFIRMED and v.variant_type == VariantType.DISCOVERED:
        v.variant_type = VariantType.RESEARCHER_CONFIRMED
    audit(db, user, "review", "name_variant", v.id, previous={"status": prev},
          new={"status": body.confirmation_status.value})
    db.commit()
    return v


@router.post("/researchers/{researcher_id}/employment", response_model=s.EmploymentOut, status_code=201)
def add_employment(researcher_id: uuid.UUID, body: s.EmploymentIn, db: Session = Depends(get_db),
                   user: User = Depends(require_admin)):
    r = get_researcher_for(db, user, researcher_id)
    if body.start_date and body.end_date and body.end_date < body.start_date:
        raise HTTPException(422, "end_date precedes start_date")
    e = EmploymentHistory(researcher_id=r.id, **body.model_dump())
    db.add(e)
    db.flush()
    audit(db, user, "create", "employment_history", e.id, new=body.model_dump(mode="json"))
    db.commit()
    return e


@router.get("/researchers/{researcher_id}/matches", response_model=list[s.QueueItem])
def researcher_matches(researcher_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Every candidate, confirmed and rejected match for one researcher, newest publications first."""
    r = get_researcher_for(db, user, researcher_id)
    rows = db.execute(
        select(IdentityMatch, Publication, InstitutionalAttribution)
        .join(Publication, Publication.id == IdentityMatch.publication_id)
        .outerjoin(InstitutionalAttribution,
                   (InstitutionalAttribution.publication_id == IdentityMatch.publication_id)
                   & (InstitutionalAttribution.researcher_id == IdentityMatch.researcher_id))
        .where(IdentityMatch.researcher_id == r.id)
        .order_by(Publication.publication_year.desc().nulls_last(), Publication.title)
    )
    return [s.QueueItem(match=m, publication=p, attribution=a, researcher=r) for m, p, a in rows]
