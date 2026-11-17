"""Discovery orchestration (§7.5): build queries, run each source, record every
search run, then ingest → deduplicate → match → assess attribution.

Each query is committed on its own, so a failure in one source is logged on its
search_run and does not lose the work of the others; re-running is idempotent.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from furis.config import Settings, get_settings
from furis.discovery.attribution import FuDetector, Period, assess
from furis.discovery.dedup import resolve
from furis.discovery.matching import MatchResult, ResearcherProfile, _surname, alias_to_parts, match_candidate
from furis.discovery.names import generate_variants, normalise_name
from furis.discovery.sources.base import Candidate, HttpClient, Query, Source, SourceError
from furis.discovery.sources.crossref import CrossrefSource
from furis.discovery.sources.openalex import OpenAlexSource
from furis.discovery.sources.orcid import OrcidSource
from furis.discovery.text import normalise_doi, normalise_title
from furis.models import (
    ConfirmationStatus,
    DuplicateCandidate,
    IdentifierType,
    IdentityMatch,
    InstitutionalAttribution,
    MatchConfidence,
    MatchStatus,
    NameVariant,
    Publication,
    PublicationAffiliation,
    PublicationAuthor,
    PublicationSource,
    Researcher,
    RunStatus,
    SearchRun,
    VariantType,
    utcnow,
)

log = logging.getLogger(__name__)

_CONF_ORDER = {MatchConfidence.REJECTED: 0, MatchConfidence.LOW: 1, MatchConfidence.MEDIUM: 2, MatchConfidence.HIGH: 3}


# ---------------------------------------------------------------------------
# Researcher setup helpers
# ---------------------------------------------------------------------------


def ensure_system_variants(db: Session, r: Researcher) -> int:
    existing = {v.normalised_name for v in r.name_variants}
    added = 0
    for v in generate_variants(r.first_name, r.middle_name, r.last_name):
        n = normalise_name(v)
        if n in existing:
            continue
        existing.add(n)
        r.name_variants.append(
            NameVariant(
                variant_name=v,
                normalised_name=n,
                variant_type=VariantType.SYSTEM_GENERATED,
                confirmation_status=ConfirmationStatus.CONFIRMED,  # derived from the registered name
                source="generator",
            )
        )
        added += 1
    return added


def build_profile(db: Session, r: Researcher) -> ResearcherProfile:
    confirmed_aliases = [
        v for v in r.name_variants
        if v.variant_type != VariantType.SYSTEM_GENERATED and v.confirmation_status == ConfirmationStatus.CONFIRMED
    ]
    coauthors: set[str] = set()
    confirmed_pubs = select(IdentityMatch.publication_id, IdentityMatch.author_position).where(
        IdentityMatch.researcher_id == r.id, IdentityMatch.match_status == MatchStatus.CONFIRMED
    )
    for pub_id, pos in db.execute(confirmed_pubs):
        for a in db.scalars(select(PublicationAuthor).where(PublicationAuthor.publication_id == pub_id)):
            if a.author_position != pos and a.researcher_id != r.id:
                s = _surname(a.raw_author_name)
                if s:
                    coauthors.add(s)
    coauthors.discard(normalise_name(r.last_name).replace(" ", ""))
    return ResearcherProfile(
        id=r.id,
        first=r.first_name,
        middle=r.middle_name,
        last=r.last_name,
        aliases=[p for p in (alias_to_parts(v.variant_name) for v in confirmed_aliases) if p],
        confirmed_variant_norms={v.normalised_name for v in confirmed_aliases},
        verified_orcids={
            i.identifier_value for i in r.identifiers if i.identifier_type == IdentifierType.ORCID and i.verified
        },
        confirmed_openalex_ids={
            i.identifier_value for i in r.identifiers if i.identifier_type == IdentifierType.OPENALEX and i.verified
        },
        known_coauthor_surnames=coauthors,
    )


def build_queries(r: Researcher, prof: ResearcherProfile) -> list[Query]:
    qs: list[Query] = []
    for orcid in sorted(prof.verified_orcids):
        qs += [Query("orcid", "orcid", orcid), Query("openalex", "orcid", orcid), Query("crossref", "orcid", orcid)]
    for oa in sorted(prof.confirmed_openalex_ids):
        qs.append(Query("openalex", "openalex_author_id", oa))

    # Name searches: confirmed variants only (generated + researcher-confirmed).
    # Discovered-but-unconfirmed names are never searched (§7.2).
    seen: set[frozenset[str]] = set()
    for v in r.name_variants:
        if v.confirmation_status != ConfirmationStatus.CONFIRMED:
            continue
        toks = v.normalised_name.split()
        if len(toks) < 2:
            continue
        key = frozenset(toks)  # name order / commas do not change a search
        if key in seen:
            continue
        seen.add(key)
        qs.append(Query("openalex", "raw_author_name", v.variant_name))
    for first, middle, last in prof.names:
        full = " ".join(p for p in (first, middle, last) if p)
        qs.append(Query("crossref", "crossref_author", full))
    return qs


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


@dataclass
class RunSummary:
    batch_id: uuid.UUID
    queries: int
    failed: int
    new_publications: int
    matches: int


class DiscoveryEngine:
    def __init__(self, db: Session, settings: Settings | None = None, sources: list[Source] | None = None):
        self.db = db
        self.settings = settings or get_settings()
        if sources is None:
            http = HttpClient(self.settings)
            sources = [OpenAlexSource(http, self.settings), CrossrefSource(http, self.settings),
                       OrcidSource(http, self.settings)]
        self.sources = {s.name: s for s in sources}
        self.fu = FuDetector(self.settings)

    def run_for_researcher(self, researcher_id: uuid.UUID) -> RunSummary:
        r = self.db.get(Researcher, researcher_id)
        if r is None:
            raise ValueError(f"researcher {researcher_id} not found")
        ensure_system_variants(self.db, r)
        self.db.commit()
        prof = build_profile(self.db, r)
        periods = [Period(e.start_date, e.end_date, e.is_fountain_university) for e in r.employment]
        batch = uuid.uuid4()
        failed = new_total = match_total = 0
        queries = [q for q in build_queries(r, prof) if q.source_name in self.sources]

        for q in queries:
            run = SearchRun(batch_id=batch, researcher_id=r.id, source_name=q.source_name,
                            search_query=q.value, query_type=q.query_type)
            self.db.add(run)
            self.db.commit()
            try:
                res = self.sources[q.source_name].run(q)
                run.records_found = res.records_found
                new = matched = 0
                for c in res.candidates:
                    if not c.title or not c.source_record_id:
                        continue
                    pub, is_new = self._ingest(c)
                    new += is_new
                    run.records_processed += 1
                    m = match_candidate(c, prof, self.fu)
                    if m:
                        self._record_match(pub, r, c, m, periods)
                        matched += 1
                run.unique_records_found = new
                run.candidates_matched = matched
                run.run_status = RunStatus.TRUNCATED if res.truncated else RunStatus.COMPLETED
                new_total += new
                match_total += matched
            except (SourceError, ValueError) as e:
                self.db.rollback()
                run = self.db.merge(run)
                run.run_status = RunStatus.FAILED
                run.error_message = str(e)[:2000]
                failed += 1
                log.warning("query failed %s/%s %r: %s", q.source_name, q.query_type, q.value, e)
            run.completed_at = utcnow()
            self.db.commit()
        return RunSummary(batch, len(queries), failed, new_total, match_total)

    # -- ingest -------------------------------------------------------------

    def _ingest(self, c: Candidate) -> tuple[Publication, bool]:
        c.doi = normalise_doi(c.doi)  # never trust a source adapter to have normalised it
        src = self.db.scalar(select(PublicationSource).where(
            PublicationSource.source_name == c.source_name, PublicationSource.source_record_id == c.source_record_id))
        if src:
            src.raw_metadata, src.retrieved_at, src.citation_count = c.raw, utcnow(), c.citation_count
            pub = src.publication
            pub.last_retrieved_at = utcnow()
            self._fill_empty(pub, c)
            return pub, False

        res = resolve(self.db, c)
        is_new = res.publication is None
        pub = res.publication or Publication(title=c.title, normalised_title=normalise_title(c.title))
        self._fill_empty(pub, c)
        pub.last_retrieved_at = utcnow()
        if is_new:
            self.db.add(pub)
            self.db.flush()
        if not pub.authors and c.authors:
            for a in c.authors:
                pub.authors.append(PublicationAuthor(raw_author_name=a.raw_name[:512], author_position=a.position,
                                                     orcid=a.orcid, source_author_id=a.source_author_id))
        pub.sources.append(PublicationSource(
            source_name=c.source_name, source_record_id=c.source_record_id, source_url=c.source_url,
            citation_count=c.citation_count, raw_metadata=c.raw))
        for other, sim in res.possible_duplicates:
            if other.id == pub.id:
                continue
            a, b = sorted([pub.id, other.id], key=str)
            exists = self.db.scalar(select(DuplicateCandidate).where(
                DuplicateCandidate.publication_id == a, DuplicateCandidate.other_publication_id == b))
            if not exists:
                self.db.add(DuplicateCandidate(publication_id=a, other_publication_id=b, similarity=sim,
                                               reason="title similarity without DOI confirmation"))
        self.db.flush()
        return pub, is_new

    @staticmethod
    def _fill_empty(pub: Publication, c: Candidate) -> None:
        """Fill canonical fields only where empty; never overwrite another source's value."""
        for attr in ("doi", "publication_year", "publication_date", "document_type", "journal_name",
                     "publisher", "issn", "landing_page_url", "is_open_access"):
            if getattr(pub, attr) is None and getattr(c, attr) is not None:
                setattr(pub, attr, getattr(c, attr))

    # -- matching / attribution --------------------------------------------

    def _record_match(self, pub: Publication, r: Researcher, c: Candidate, m: MatchResult,
                      periods: list[Period]) -> None:
        a = m.author
        evidence = m.evidence | {"source": c.source_name, "source_record_id": c.source_record_id}
        im = self.db.scalar(select(IdentityMatch).where(
            IdentityMatch.publication_id == pub.id, IdentityMatch.researcher_id == r.id))
        if im is None:
            im = IdentityMatch(publication_id=pub.id, researcher_id=r.id, author_position=a.position if a else None,
                               matching_method=m.method, confidence=m.confidence, confidence_score=m.score,
                               evidence_summary={"sources": [evidence]})
            self.db.add(im)
        elif im.match_status == MatchStatus.CANDIDATE:
            # Human decisions are never overwritten; candidates accumulate evidence.
            ev = dict(im.evidence_summary or {})
            ev["sources"] = [*ev.get("sources", []), evidence][-10:]
            im.evidence_summary = ev
            if _CONF_ORDER[m.confidence] > _CONF_ORDER[im.confidence] or m.confidence == MatchConfidence.REJECTED:
                im.confidence, im.confidence_score, im.matching_method = m.confidence, m.score, m.method
                if a:
                    im.author_position = a.position

        if a:
            for raw in a.raw_affiliations or a.institution_names:
                exists = self.db.scalar(select(PublicationAffiliation).where(
                    PublicationAffiliation.publication_id == pub.id, PublicationAffiliation.researcher_id == r.id,
                    PublicationAffiliation.raw_affiliation == raw,
                    PublicationAffiliation.source_name == c.source_name))
                if not exists:
                    self.db.add(PublicationAffiliation(
                        publication_id=pub.id, researcher_id=r.id, author_position=a.position, raw_affiliation=raw,
                        normalised_institution=a.institution_names[0] if a.institution_names else None,
                        institution_identifier=a.institution_ids[0] if a.institution_ids else None,
                        is_fountain_university=self.fu.text_is_fu(raw) or self.fu.author_is_fu(a),
                        source_name=c.source_name))
            self._maybe_discover_variant(r, a.raw_name, m)

        if m.confidence != MatchConfidence.REJECTED:
            self.db.flush()
            self._assess_attribution(pub, r, periods)

    def _maybe_discover_variant(self, r: Researcher, raw: str, m: MatchResult) -> None:
        # Recursive discovery (§7.6): names seen on identifier-backed matches become
        # Category 3 variants, pending researcher confirmation. Never auto-searched.
        if m.method not in ("orcid", "openalex_author_id"):
            return
        n = normalise_name(raw)
        if not n or any(v.normalised_name == n for v in r.name_variants):
            return
        r.name_variants.append(NameVariant(variant_name=raw[:255], normalised_name=n,
                                           variant_type=VariantType.DISCOVERED,
                                           confirmation_status=ConfirmationStatus.PENDING, source=m.method))

    def _assess_attribution(self, pub: Publication, r: Researcher, periods: list[Period]) -> None:
        affs = list(self.db.scalars(select(PublicationAffiliation).where(
            PublicationAffiliation.publication_id == pub.id, PublicationAffiliation.researcher_id == r.id)))
        status, ev = assess(
            pub_date=pub.publication_date, pub_year=pub.publication_year,
            has_fu_affiliation=any(x.is_fountain_university for x in affs),
            other_affiliations=sorted({x.raw_affiliation for x in affs if not x.is_fountain_university}),
            has_affiliation_data=bool(affs), periods=periods)
        ia = self.db.scalar(select(InstitutionalAttribution).where(
            InstitutionalAttribution.publication_id == pub.id, InstitutionalAttribution.researcher_id == r.id))
        if ia is None:
            self.db.add(InstitutionalAttribution(publication_id=pub.id, researcher_id=r.id, suggested_status=status,
                                                 evidence=ev, policy_version=ev["policy_version"]))
        elif ia.final_status is None:
            ia.suggested_status, ia.evidence, ia.policy_version = status, ev, ev["policy_version"]
