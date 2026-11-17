"""Verification portal endpoints (Module 5, §16).

Authorship and attribution are separate decisions with separate permissions:
- authorship: the researcher themself, or Research Office / Super Admin;
- attribution: Research Office / Super Admin only, and FU-output statuses require
  confirmed authorship first. A researcher confirming authorship never approves
  institutional attribution (§16).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from furis import schemas as s
from furis.api.deps import ADMIN_ROLES, audit, current_user, get_researcher_for, require_admin
from furis.db import get_db
from furis.discovery.names import best_comparison
from furis.models import (
    AttributionStatus,
    DuplicateCandidate,
    DuplicateStatus,
    IdentityMatch,
    InstitutionalAttribution,
    MatchConfidence,
    MatchStatus,
    Publication,
    PublicationAffiliation,
    PublicationAuthor,
    PublicationSource,
    Researcher,
    User,
    UserRole,
    VerificationRecord,
    VerificationType,
    utcnow,
)

router = APIRouter(prefix="/verification", tags=["verification"])

_CONF_RANK = case(
    (IdentityMatch.confidence == MatchConfidence.HIGH, 3),
    (IdentityMatch.confidence == MatchConfidence.MEDIUM, 2),
    (IdentityMatch.confidence == MatchConfidence.LOW, 1),
    else_=0,
)


@router.get("/queue", response_model=list[s.QueueItem])
def queue(
    researcher_id: uuid.UUID | None = None, confidence: MatchConfidence | None = None,
    limit: int = Query(50, le=200), offset: int = 0,
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    stmt = (
        select(IdentityMatch, Publication, InstitutionalAttribution, Researcher)
        .join(Publication, Publication.id == IdentityMatch.publication_id)
        .join(Researcher, Researcher.id == IdentityMatch.researcher_id)
        .outerjoin(InstitutionalAttribution,
                   (InstitutionalAttribution.publication_id == IdentityMatch.publication_id)
                   & (InstitutionalAttribution.researcher_id == IdentityMatch.researcher_id))
        .where(IdentityMatch.match_status == MatchStatus.CANDIDATE,
               IdentityMatch.confidence != MatchConfidence.REJECTED)
        .order_by(_CONF_RANK.desc(), IdentityMatch.confidence_score.desc())
    )
    if user.role == UserRole.RESEARCHER:
        stmt = stmt.where(IdentityMatch.researcher_id == user.researcher_id)
    elif user.role == UserRole.FACULTY_ADMIN:
        stmt = stmt.where(Researcher.faculty_id == user.faculty_id)
    if researcher_id:
        stmt = stmt.where(IdentityMatch.researcher_id == researcher_id)
    if confidence:
        stmt = stmt.where(IdentityMatch.confidence == confidence)
    return [
        s.QueueItem(match=m, publication=p, attribution=a, researcher=r)
        for m, p, a, r in db.execute(stmt.limit(limit).offset(offset))
    ]


@router.get("/attribution-queue", response_model=list[s.QueueItem])
def attribution_queue(
    researcher_id: uuid.UUID | None = None, limit: int = Query(50, le=200), offset: int = 0,
    db: Session = Depends(get_db), user: User = Depends(require_admin),
):
    """Confirmed authorships whose institutional attribution has not been decided."""
    stmt = (
        select(IdentityMatch, Publication, InstitutionalAttribution, Researcher)
        .join(Publication, Publication.id == IdentityMatch.publication_id)
        .join(Researcher, Researcher.id == IdentityMatch.researcher_id)
        .outerjoin(InstitutionalAttribution,
                   (InstitutionalAttribution.publication_id == IdentityMatch.publication_id)
                   & (InstitutionalAttribution.researcher_id == IdentityMatch.researcher_id))
        .where(IdentityMatch.match_status == MatchStatus.CONFIRMED, InstitutionalAttribution.final_status.is_(None))
        .order_by(Publication.publication_year.desc().nulls_last(), Publication.title)
    )
    if researcher_id:
        stmt = stmt.where(IdentityMatch.researcher_id == researcher_id)
    return [s.QueueItem(match=m, publication=p, attribution=a, researcher=r)
            for m, p, a, r in db.execute(stmt.limit(limit).offset(offset))]


def _get_match(db: Session, pub_id: uuid.UUID, rid: uuid.UUID) -> IdentityMatch:
    m = db.scalar(select(IdentityMatch).where(IdentityMatch.publication_id == pub_id,
                                              IdentityMatch.researcher_id == rid))
    if not m:
        raise HTTPException(404, "no candidate match for this publication and researcher")
    return m


def _link_author(db: Session, m: IdentityMatch, r: Researcher, link: bool) -> None:
    authors = list(db.scalars(select(PublicationAuthor).where(PublicationAuthor.publication_id == m.publication_id)))
    target = next((a for a in authors if a.author_position == m.author_position), None)
    names = [(r.first_name, r.middle_name, r.last_name)]
    if target is None or best_comparison(target.raw_author_name, names).score == 0:
        # Canonical author list came from a different source; pick by name.
        scored = sorted(authors, key=lambda a: best_comparison(a.raw_author_name, names).score, reverse=True)
        target = scored[0] if scored and best_comparison(scored[0].raw_author_name, names).score > 0 else None
    if target is None:
        return
    if link:
        target.researcher_id, target.identity_status = r.id, MatchStatus.CONFIRMED
        target.confidence_score = m.confidence_score
    elif target.researcher_id == r.id:
        target.researcher_id, target.identity_status = None, MatchStatus.REJECTED


@router.post("/authorship", response_model=s.MatchOut)
def decide_authorship(body: s.AuthorshipDecision, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if body.decision == MatchStatus.CANDIDATE:
        raise HTTPException(422, "decision must be confirmed or rejected")
    r = get_researcher_for(db, user, body.researcher_id)
    if user.role not in ADMIN_ROLES and user.researcher_id != r.id:
        raise HTTPException(403, "only the researcher or the Research Office may decide authorship")
    m = _get_match(db, body.publication_id, r.id)
    prev = m.match_status.value
    m.match_status, m.reviewed_by, m.reviewed_at = body.decision, user.id, utcnow()
    _link_author(db, m, r, body.decision == MatchStatus.CONFIRMED)
    db.add(VerificationRecord(publication_id=m.publication_id, researcher_id=r.id,
                              verification_type=VerificationType.AUTHORSHIP, decision=body.decision.value,
                              reviewer_id=user.id, evidence=body.evidence, comments=body.comments))
    if body.decision == MatchStatus.REJECTED:
        ia = db.scalar(select(InstitutionalAttribution).where(
            InstitutionalAttribution.publication_id == m.publication_id, InstitutionalAttribution.researcher_id == r.id))
        if ia and ia.final_status != AttributionStatus.NOT_ATTRIBUTABLE:
            # Without authorship, this researcher cannot carry FU attribution for the paper.
            ia.final_status, ia.decided_by, ia.decided_at = AttributionStatus.NOT_ATTRIBUTABLE, user.id, utcnow()
    audit(db, user, "authorship_decision", "identity_match", m.id, previous={"status": prev},
          new={"status": body.decision.value, "comments": body.comments})
    db.commit()
    return m


@router.post("/attribution", response_model=s.AttributionOut)
def decide_attribution(body: s.AttributionDecision, db: Session = Depends(get_db),
                       user: User = Depends(require_admin)):
    r = get_researcher_for(db, user, body.researcher_id)
    m = _get_match(db, body.publication_id, r.id)
    needs_author = {AttributionStatus.CONFIRMED_FU_OUTPUT, AttributionStatus.RESEARCHER_PUBLICATION_NOT_FU}
    if body.status in needs_author and m.match_status != MatchStatus.CONFIRMED:
        raise HTTPException(409, "authorship must be confirmed before this attribution status")
    if body.status == AttributionStatus.CONFIRMED_FU_OUTPUT and not (body.evidence or body.comments):
        raise HTTPException(422, "record the evidence or reasoning for confirming FU output")
    ia = db.scalar(select(InstitutionalAttribution).where(
        InstitutionalAttribution.publication_id == m.publication_id, InstitutionalAttribution.researcher_id == r.id))
    if ia is None:
        ia = InstitutionalAttribution(publication_id=m.publication_id, researcher_id=r.id,
                                      suggested_status=AttributionStatus.UNDER_REVIEW, evidence={},
                                      policy_version="manual")
        db.add(ia)
    prev = ia.final_status.value if ia.final_status else None
    ia.final_status, ia.decided_by, ia.decided_at = body.status, user.id, utcnow()
    db.add(VerificationRecord(publication_id=m.publication_id, researcher_id=r.id,
                              verification_type=VerificationType.ATTRIBUTION, decision=body.status.value,
                              reviewer_id=user.id, evidence=body.evidence, comments=body.comments))
    db.flush()
    audit(db, user, "attribution_decision", "institutional_attribution", ia.id, previous={"final_status": prev},
          new={"final_status": body.status.value, "comments": body.comments})
    db.commit()
    return ia


@router.get("/history")
def history(publication_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    recs = db.scalars(select(VerificationRecord).where(VerificationRecord.publication_id == publication_id)
                      .order_by(VerificationRecord.verified_at)).all()
    out = []
    for v in recs:
        r = db.get(Researcher, v.researcher_id)
        if r and (user.role in ADMIN_ROLES or user.researcher_id == r.id
                  or (user.role == UserRole.FACULTY_ADMIN and user.faculty_id == r.faculty_id)):
            reviewer = db.get(User, v.reviewer_id)
            out.append({"type": v.verification_type.value, "decision": v.decision, "researcher_id": str(r.id),
                        "reviewer_id": str(v.reviewer_id), "reviewer_name": reviewer.full_name if reviewer else None,
                        "evidence": v.evidence, "comments": v.comments,
                        "verified_at": v.verified_at.isoformat()})
    return out


# -- duplicates ----------------------------------------------------------------

dup_router = APIRouter(prefix="/duplicates", tags=["deduplication"])


@dup_router.get("", response_model=list[s.DuplicateOut])
def list_duplicates(status: DuplicateStatus = DuplicateStatus.PENDING, db: Session = Depends(get_db),
                    _: User = Depends(require_admin)):
    out = []
    for d in db.scalars(select(DuplicateCandidate).where(DuplicateCandidate.status == status)
                        .order_by(DuplicateCandidate.similarity.desc())):
        item = s.DuplicateOut.model_validate(d)
        a, b = db.get(Publication, d.publication_id), db.get(Publication, d.other_publication_id)
        item.publication = s.PublicationOut.model_validate(a) if a else None
        item.other_publication = s.PublicationOut.model_validate(b) if b else None
        out.append(item)
    return out


@dup_router.post("/{dup_id}", response_model=s.DuplicateOut)
def decide_duplicate(dup_id: uuid.UUID, body: s.DuplicateDecision, db: Session = Depends(get_db),
                     user: User = Depends(require_admin)):
    d = db.get(DuplicateCandidate, dup_id)
    if not d or d.status != DuplicateStatus.PENDING:
        raise HTTPException(404, "pending duplicate not found")
    if body.status == DuplicateStatus.MERGED:
        _merge(db, keep_id=d.publication_id, drop_id=d.other_publication_id, user=user)
    d.status = body.status
    audit(db, user, "duplicate_decision", "duplicate_candidate", d.id, new={"status": body.status.value})
    db.commit()
    return d


def _merge(db: Session, keep_id: uuid.UUID, drop_id: uuid.UUID, user: User) -> None:
    keep, drop = db.get(Publication, keep_id), db.get(Publication, drop_id)
    if not keep or not drop:
        raise HTTPException(404, "publication missing")
    if keep.doi is None and drop.doi:
        keep_id, drop_id, keep, drop = drop_id, keep_id, drop, keep  # keep the DOI-bearing record
    snapshot = {"title": drop.title, "doi": drop.doi, "year": drop.publication_year}
    for src in db.scalars(select(PublicationSource).where(PublicationSource.publication_id == drop.id)):
        src.publication_id = keep.id
    for aff in db.scalars(select(PublicationAffiliation).where(PublicationAffiliation.publication_id == drop.id)):
        aff.publication_id = keep.id
    for v in db.scalars(select(VerificationRecord).where(VerificationRecord.publication_id == drop.id)):
        v.publication_id = keep.id
    for model in (IdentityMatch, InstitutionalAttribution):
        for row in db.scalars(select(model).where(model.publication_id == drop.id)):
            clash = db.scalar(select(model).where(model.publication_id == keep.id,
                                                  model.researcher_id == row.researcher_id))
            if clash is None:
                row.publication_id = keep.id
            else:
                # Keep the reviewed decision; otherwise keep the existing row.
                reviewed = (getattr(row, "match_status", None) not in (None, MatchStatus.CANDIDATE)
                            or getattr(row, "final_status", None) is not None)
                if reviewed:
                    db.delete(clash)
                    db.flush()
                    row.publication_id = keep.id
                else:
                    db.delete(row)
    for dc in db.scalars(select(DuplicateCandidate).where(
            (DuplicateCandidate.publication_id == drop.id) | (DuplicateCandidate.other_publication_id == drop.id))):
        if dc.status == DuplicateStatus.PENDING and {dc.publication_id, dc.other_publication_id} != {keep.id, drop.id}:
            dc.status = DuplicateStatus.DISTINCT  # partner merged away; re-flagged on next discovery
        if dc.publication_id == drop.id:
            dc.publication_id = keep.id
        if dc.other_publication_id == drop.id:
            dc.other_publication_id = keep.id
    fill = {a: getattr(drop, a) for a in ("doi", "publication_year", "publication_date", "journal_name",
                                          "publisher", "landing_page_url")}
    db.flush()
    db.delete(drop)
    db.flush()  # drop's DOI must be gone before keep can take it (unique constraint)
    for attr, value in fill.items():
        if getattr(keep, attr) is None:
            setattr(keep, attr, value)
    audit(db, user, "merge", "publication", keep.id, previous={"merged_from": str(drop_id), **snapshot})
