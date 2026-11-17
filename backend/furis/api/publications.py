from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from furis import schemas as s
from furis.api.deps import ADMIN_ROLES, current_user
from furis.db import get_db
from furis.models import (
    AttributionStatus,
    IdentifierType,
    IdentityMatch,
    InstitutionalAttribution,
    MatchStatus,
    Publication,
    Researcher,
    ResearcherIdentifier,
    SearchRun,
    User,
    UserRole,
)

router = APIRouter(tags=["publications"])


def _scope(stmt, user: User):
    if user.role == UserRole.RESEARCHER:
        return stmt.where(Researcher.id == user.researcher_id)
    if user.role == UserRole.FACULTY_ADMIN:
        return stmt.where(Researcher.faculty_id == user.faculty_id)
    return stmt


@router.get("/publications", response_model=list[s.PublicationOut])
def list_publications(
    researcher_id: uuid.UUID | None = None, match_status: MatchStatus | None = None,
    attribution_status: AttributionStatus | None = None, year: int | None = None,
    limit: int = Query(100, le=500), offset: int = 0,
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    """Publications linked to researchers. `attribution_status` filters the
    *final* (reviewed) status; unreviewed rows use their suggested status."""
    sub = (select(IdentityMatch.publication_id)
           .join(Researcher, Researcher.id == IdentityMatch.researcher_id))
    sub = _scope(sub, user)
    if researcher_id:
        sub = sub.where(IdentityMatch.researcher_id == researcher_id)
    if match_status:
        sub = sub.where(IdentityMatch.match_status == match_status)
    if attribution_status:
        sub = sub.join(InstitutionalAttribution,
                       (InstitutionalAttribution.publication_id == IdentityMatch.publication_id)
                       & (InstitutionalAttribution.researcher_id == IdentityMatch.researcher_id)).where(
            func.coalesce(InstitutionalAttribution.final_status, InstitutionalAttribution.suggested_status)
            == attribution_status)
    stmt = select(Publication).where(Publication.id.in_(sub))
    if year:
        stmt = stmt.where(Publication.publication_year == year)
    stmt = stmt.order_by(Publication.publication_year.desc().nulls_last(), Publication.title)
    return db.scalars(stmt.limit(limit).offset(offset)).all()


@router.get("/publications/{publication_id}", response_model=s.PublicationDetail)
def get_publication(publication_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    pub = db.get(Publication, publication_id)
    if not pub:
        raise HTTPException(404)
    m_stmt = _scope(select(IdentityMatch).join(Researcher, Researcher.id == IdentityMatch.researcher_id)
                    .where(IdentityMatch.publication_id == pub.id), user)
    matches = db.scalars(m_stmt).all()
    if user.role not in ADMIN_ROLES and not matches:
        raise HTTPException(404)
    a_stmt = _scope(select(InstitutionalAttribution)
                    .join(Researcher, Researcher.id == InstitutionalAttribution.researcher_id)
                    .where(InstitutionalAttribution.publication_id == pub.id), user)
    out = s.PublicationDetail.model_validate(pub)
    out.matches = [s.MatchOut.model_validate(m) for m in matches]
    out.attributions = [s.AttributionOut.model_validate(a) for a in db.scalars(a_stmt)]
    return out


@router.get("/analytics/summary")
def summary(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Basic indicators (§15.1, §15.3). FU output counts only reviewer-confirmed rows."""
    if user.role == UserRole.RESEARCHER:
        raise HTTPException(403)
    rs = _scope(select(Researcher.id).where(Researcher.archived_at.is_(None)), user)
    researcher_ids = set(db.scalars(rs))
    n_res = len(researcher_ids) or 1

    def count_pubs(*conds, model=IdentityMatch):
        q = select(func.count(distinct(model.publication_id))).where(model.researcher_id.in_(researcher_ids), *conds)
        return db.scalar(q) or 0

    fu_final = InstitutionalAttribution.final_status == AttributionStatus.CONFIRMED_FU_OUTPUT
    by_year = db.execute(
        select(Publication.publication_year, func.count(distinct(Publication.id)))
        .join(InstitutionalAttribution, InstitutionalAttribution.publication_id == Publication.id)
        .where(fu_final, InstitutionalAttribution.researcher_id.in_(researcher_ids))
        .group_by(Publication.publication_year).order_by(Publication.publication_year)
    ).all()
    by_faculty = db.execute(
        select(Researcher.faculty_id, func.count(distinct(InstitutionalAttribution.publication_id)))
        .join(InstitutionalAttribution, InstitutionalAttribution.researcher_id == Researcher.id)
        .where(fu_final, Researcher.id.in_(researcher_ids)).group_by(Researcher.faculty_id)
    ).all()
    verified_orcid = db.scalar(select(func.count(distinct(ResearcherIdentifier.researcher_id))).where(
        ResearcherIdentifier.identifier_type == IdentifierType.ORCID, ResearcherIdentifier.verified.is_(True),
        ResearcherIdentifier.researcher_id.in_(researcher_ids))) or 0
    with_confirmed = db.scalar(select(func.count(distinct(IdentityMatch.researcher_id))).where(
        IdentityMatch.match_status == MatchStatus.CONFIRMED, IdentityMatch.researcher_id.in_(researcher_ids))) or 0
    runs = dict(db.execute(select(SearchRun.run_status, func.count()).where(
        SearchRun.researcher_id.in_(researcher_ids)).group_by(SearchRun.run_status)).all())
    return {
        "researchers": len(researcher_ids),
        "publications_discovered": count_pubs(),
        "confirmed_researcher_publications": count_pubs(IdentityMatch.match_status == MatchStatus.CONFIRMED),
        "awaiting_authorship_review": count_pubs(IdentityMatch.match_status == MatchStatus.CANDIDATE),
        "confirmed_fu_output": count_pubs(fu_final, model=InstitutionalAttribution),
        "awaiting_attribution_review": count_pubs(InstitutionalAttribution.final_status.is_(None),
                                                  model=InstitutionalAttribution),
        "fu_output_by_year": [{"year": y, "count": c} for y, c in by_year],
        "fu_output_by_faculty": [{"faculty_id": str(f) if f else None, "count": c} for f, c in by_faculty],
        "pct_researchers_verified_orcid": round(100 * verified_orcid / n_res, 1),
        "pct_researchers_with_confirmed_publications": round(100 * with_confirmed / n_res, 1),
        "search_runs_by_status": {k.value: v for k, v in runs.items()},
    }
