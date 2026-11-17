"""Public, read-only research view (brief §13.5). No sign-in.

Shows only what the Research Desk has confirmed:
- a researcher's publications are those whose authorship is confirmed;
- Fountain University output is publications whose attribution is confirmed.

Never exposed here: candidates, rejected matches, evidence, verification history,
email addresses, staff numbers, employment dates or unverified identifiers.
Researchers appear only once they have at least one confirmed publication.
Switch the whole view off with FURIS_PUBLIC_VIEW=false.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from furis.config import Settings, get_settings
from furis.db import get_db
from furis.models import (
    AttributionStatus,
    Department,
    Faculty,
    IdentifierType,
    IdentityMatch,
    InstitutionalAttribution,
    MatchStatus,
    Publication,
    Researcher,
    ResearcherIdentifier,
)

router = APIRouter(prefix="/public", tags=["public"])


def _enabled(settings: Settings = Depends(get_settings)) -> None:
    if not settings.public_view:
        raise HTTPException(404)


CONFIRMED = IdentityMatch.match_status == MatchStatus.CONFIRMED
FU_FINAL = InstitutionalAttribution.final_status == AttributionStatus.CONFIRMED_FU_OUTPUT
ACTIVE = Researcher.archived_at.is_(None)


class PublicPerson(BaseModel):
    id: uuid.UUID
    name: str
    faculty: str | None
    department: str | None


class PublicPublication(BaseModel):
    id: uuid.UUID
    title: str
    doi: str | None
    publication_year: int | None
    publication_date: date | None
    journal_name: str | None
    document_type: str | None
    landing_page_url: str | None
    is_open_access: bool | None
    fu_output: bool
    researchers: list[PublicPerson]


class PublicResearcher(PublicPerson):
    orcid: str | None
    publication_count: int
    fu_output_count: int


class PublicResearcherDetail(PublicResearcher):
    publications: list[PublicPublication]


class PublicSummary(BaseModel):
    fu_output: int
    researcher_publications: int
    researchers: int
    fu_output_by_year: list[dict]
    faculties: list[dict]


def _name(r: Researcher) -> str:
    if r.preferred_name:
        return r.preferred_name
    return " ".join(p for p in (r.first_name, r.middle_name, r.last_name) if p)


def _people(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, PublicPerson]:
    if not ids:
        return {}
    fac = {f.id: f.name for f in db.scalars(select(Faculty))}
    dep = {d.id: d.name for d in db.scalars(select(Department))}
    return {r.id: PublicPerson(id=r.id, name=_name(r), faculty=fac.get(r.faculty_id), department=dep.get(r.department_id))
            for r in db.scalars(select(Researcher).where(Researcher.id.in_(ids), ACTIVE))}


def _publications(db: Session, pub_ids: list[uuid.UUID]) -> list[PublicPublication]:
    if not pub_ids:
        return []
    pubs = {p.id: p for p in db.scalars(select(Publication).where(Publication.id.in_(pub_ids)))}
    authors: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for pid, rid in db.execute(select(IdentityMatch.publication_id, IdentityMatch.researcher_id)
                               .where(IdentityMatch.publication_id.in_(pub_ids), CONFIRMED)):
        authors[pid].add(rid)
    fu = set(db.scalars(select(InstitutionalAttribution.publication_id)
                        .where(InstitutionalAttribution.publication_id.in_(pub_ids), FU_FINAL)))
    people = _people(db, {r for rs in authors.values() for r in rs})
    out = []
    for pid in pub_ids:
        p = pubs.get(pid)
        if not p:
            continue
        out.append(PublicPublication(
            id=p.id, title=p.title, doi=p.doi, publication_year=p.publication_year, publication_date=p.publication_date,
            journal_name=p.journal_name, document_type=p.document_type, landing_page_url=p.landing_page_url,
            is_open_access=p.is_open_access, fu_output=p.id in fu,
            researchers=sorted((people[r] for r in authors[pid] if r in people), key=lambda x: x.name)))
    return out


@router.get("/summary", response_model=PublicSummary, dependencies=[Depends(_enabled)])
def summary(db: Session = Depends(get_db)):
    fu_ids = select(InstitutionalAttribution.publication_id).join(
        Researcher, Researcher.id == InstitutionalAttribution.researcher_id).where(FU_FINAL, ACTIVE)
    by_year = db.execute(select(Publication.publication_year, func.count())
                         .where(Publication.id.in_(fu_ids)).group_by(Publication.publication_year)
                         .order_by(Publication.publication_year)).all()
    faculties = db.execute(
        select(Faculty.id, Faculty.name, func.count(distinct(InstitutionalAttribution.publication_id)))
        .join(Researcher, Researcher.faculty_id == Faculty.id)
        .join(InstitutionalAttribution, InstitutionalAttribution.researcher_id == Researcher.id)
        .where(FU_FINAL, ACTIVE).group_by(Faculty.id, Faculty.name).order_by(Faculty.name)).all()
    confirmed = select(IdentityMatch).join(Researcher, Researcher.id == IdentityMatch.researcher_id).where(CONFIRMED, ACTIVE)
    return PublicSummary(
        fu_output=db.scalar(select(func.count()).select_from(fu_ids.distinct().subquery())) or 0,
        researcher_publications=db.scalar(select(func.count(distinct(confirmed.subquery().c.publication_id)))) or 0,
        researchers=db.scalar(select(func.count(distinct(confirmed.subquery().c.researcher_id)))) or 0,
        fu_output_by_year=[{"year": y, "count": c} for y, c in by_year],
        faculties=[{"id": str(i), "name": n, "fu_output": c} for i, n, c in faculties],
    )


@router.get("/publications", response_model=list[PublicPublication], dependencies=[Depends(_enabled)])
def publications(
    scope: str = Query("fu", pattern="^(fu|all)$"), year: int | None = None, faculty_id: uuid.UUID | None = None,
    q: str | None = Query(None, max_length=200), limit: int = Query(50, le=200), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """scope=fu: confirmed Fountain University output. scope=all: every confirmed researcher publication."""
    if scope == "fu":
        link = select(InstitutionalAttribution.publication_id.label("pid"), InstitutionalAttribution.researcher_id.label("rid")
                      ).where(FU_FINAL)
    else:
        link = select(IdentityMatch.publication_id.label("pid"), IdentityMatch.researcher_id.label("rid")).where(CONFIRMED)
    link = link.subquery()
    stmt = (select(Publication.id).join(link, link.c.pid == Publication.id)
            .join(Researcher, Researcher.id == link.c.rid).where(ACTIVE))
    if year:
        stmt = stmt.where(Publication.publication_year == year)
    if faculty_id:
        stmt = stmt.where(Researcher.faculty_id == faculty_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Publication.title.ilike(like), Publication.journal_name.ilike(like),
                              Researcher.last_name.ilike(like), Researcher.first_name.ilike(like)))
    ids = db.scalars(stmt.group_by(Publication.id, Publication.publication_year, Publication.title)
                     .order_by(Publication.publication_year.desc().nulls_last(), Publication.title)
                     .limit(limit).offset(offset)).all()
    return _publications(db, list(ids))


def _researcher_rows(db: Session, stmt):
    counts = (select(IdentityMatch.researcher_id, func.count(distinct(IdentityMatch.publication_id)).label("n"))
              .where(CONFIRMED).group_by(IdentityMatch.researcher_id).subquery())
    fu = (select(InstitutionalAttribution.researcher_id, func.count(distinct(InstitutionalAttribution.publication_id)).label("n"))
          .where(FU_FINAL).group_by(InstitutionalAttribution.researcher_id).subquery())
    orcid = (select(ResearcherIdentifier.researcher_id, func.min(ResearcherIdentifier.identifier_value).label("v"))
             .where(ResearcherIdentifier.identifier_type == IdentifierType.ORCID, ResearcherIdentifier.verified.is_(True))
             .group_by(ResearcherIdentifier.researcher_id).subquery())
    stmt = (stmt.add_columns(counts.c.n, func.coalesce(fu.c.n, 0), orcid.c.v)
            .join(counts, counts.c.researcher_id == Researcher.id)
            .outerjoin(fu, fu.c.researcher_id == Researcher.id)
            .outerjoin(orcid, orcid.c.researcher_id == Researcher.id))
    rows = db.execute(stmt).all()
    people = _people(db, {r.id for r, *_ in rows})
    return [PublicResearcher(**people[r.id].model_dump(), orcid=o, publication_count=n, fu_output_count=f)
            for r, n, f, o in rows if r.id in people]


@router.get("/researchers", response_model=list[PublicResearcher], dependencies=[Depends(_enabled)])
def researchers(q: str | None = Query(None, max_length=200), faculty_id: uuid.UUID | None = None,
                db: Session = Depends(get_db)):
    stmt = select(Researcher).where(ACTIVE).order_by(Researcher.last_name, Researcher.first_name)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Researcher.last_name.ilike(like), Researcher.first_name.ilike(like),
                              Researcher.preferred_name.ilike(like)))
    if faculty_id:
        stmt = stmt.where(Researcher.faculty_id == faculty_id)
    return _researcher_rows(db, stmt)


@router.get("/researchers/{researcher_id}", response_model=PublicResearcherDetail, dependencies=[Depends(_enabled)])
def researcher(researcher_id: uuid.UUID, db: Session = Depends(get_db)):
    rows = _researcher_rows(db, select(Researcher).where(Researcher.id == researcher_id, ACTIVE))
    if not rows:
        raise HTTPException(404, "No confirmed publications for this researcher.")
    pub_ids = db.scalars(select(IdentityMatch.publication_id).join(Publication, Publication.id == IdentityMatch.publication_id)
                         .where(IdentityMatch.researcher_id == researcher_id, CONFIRMED)
                         .order_by(Publication.publication_year.desc().nulls_last(), Publication.title)).all()
    return PublicResearcherDetail(**rows[0].model_dump(), publications=_publications(db, list(pub_ids)))


@router.get("/faculties", dependencies=[Depends(_enabled)])
def faculties(db: Session = Depends(get_db)):
    return [{"id": str(f.id), "name": f.name} for f in db.scalars(select(Faculty).order_by(Faculty.name))]
