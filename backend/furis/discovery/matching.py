"""Author identity resolution (§8): deterministic identifiers first, then
conservative name comparison plus contextual evidence.

The thresholds below are PROVISIONAL (§8.4). Calibrate them with the pilot's
ground-truth dataset (`furis evaluate`) before using any class for automated
decisions. No class here auto-confirms authorship: HIGH only means "queue first".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from furis.discovery.attribution import FuDetector
from furis.discovery.names import NameComparison, best_comparison, normalise_name, parse_byline
from furis.discovery.sources.base import Candidate, CandidateAuthor
from furis.models import MatchConfidence

W_NAME, W_FU_AFFIL, W_COAUTHOR, W_CONFIRMED_ALIAS = 0.6, 0.2, 0.1, 0.05
HIGH, MEDIUM = 0.8, 0.5


@dataclass
class ResearcherProfile:
    id: object
    first: str
    middle: str | None
    last: str
    aliases: list[tuple[str, str | None, str]] = field(default_factory=list)  # confirmed only
    confirmed_variant_norms: set[str] = field(default_factory=set)
    verified_orcids: set[str] = field(default_factory=set)
    confirmed_openalex_ids: set[str] = field(default_factory=set)
    known_coauthor_surnames: set[str] = field(default_factory=set)

    @property
    def names(self) -> list[tuple[str, str | None, str]]:
        return [(self.first, self.middle, self.last), *self.aliases]


@dataclass
class MatchResult:
    confidence: MatchConfidence
    score: float
    method: str
    author: CandidateAuthor | None
    evidence: dict


def alias_to_parts(alias: str) -> tuple[str, str | None, str] | None:
    """Turn a confirmed alias string into (first, middle, last) for comparison."""
    if "," in alias:
        fam, _, giv = alias.partition(",")
        given = giv.split()
        if not given or not fam.strip():
            return None
        return given[0], " ".join(given[1:]) or None, fam.strip()
    toks = alias.split()
    if len(toks) < 2:
        return None
    return toks[0], " ".join(toks[1:-1]) or None, toks[-1]


def _surname(raw: str) -> str | None:
    p = parse_byline(raw)
    if p.family:
        return p.family
    full = [t for t in p.tokens if len(t) > 1]
    return full[-1] if full else None


def match_candidate(c: Candidate, prof: ResearcherProfile, fu: FuDetector) -> MatchResult | None:
    # ORCID-claimed record: the owner is the author.
    if c.owner_orcid:
        if c.owner_orcid in prof.verified_orcids:
            return MatchResult(MatchConfidence.HIGH, 0.97, "orcid_record", None, {"orcid": c.owner_orcid})
        return None

    scored: list[tuple[CandidateAuthor, NameComparison]] = [
        (a, best_comparison(a.raw_name, prof.names)) for a in c.authors if a.raw_name
    ]

    # 1) Deterministic identifiers on an individual authorship.
    for a, nc in scored:
        method = None
        if a.orcid and a.orcid in prof.verified_orcids:
            method, score = "orcid", 0.97
        elif a.source_author_id and a.source_author_id in prof.confirmed_openalex_ids:
            method, score = "openalex_author_id", 0.92
        if method:
            ev = {"identifier": method, "raw_name": a.raw_name, "name_kind": nc.kind}
            if nc.kind in ("conflict", "no_surname"):
                # Identifier and byline disagree: possible profile contamination (§8.1).
                ev["warning"] = "identifier_name_inconsistency"
                return MatchResult(MatchConfidence.MEDIUM, 0.6, method, a, ev)
            return MatchResult(MatchConfidence.HIGH, score, method, a, ev)

    # 2) Name-based matching.
    hits = [(a, nc) for a, nc in scored if nc.score > 0]
    if not hits:
        return None
    hits.sort(key=lambda x: x[1].score, reverse=True)
    a, nc = hits[0]
    ev: dict = {"raw_name": a.raw_name, "name_kind": nc.kind, "name_score": nc.score, "signals": []}

    if a.orcid and prof.verified_orcids and a.orcid not in prof.verified_orcids:
        ev["signals"].append(f"byline carries a different ORCID ({a.orcid})")
        return MatchResult(MatchConfidence.REJECTED, 0.0, "orcid_conflict", a, ev)

    score = W_NAME * nc.score
    if fu.author_is_fu(a):
        score += W_FU_AFFIL
        ev["signals"].append("Fountain University affiliation on this authorship")
    others = {_surname(o.raw_name) for o in c.authors if o is not a} - {None}
    shared = sorted(others & prof.known_coauthor_surnames)
    if shared:
        score += W_COAUTHOR
        ev["signals"].append(f"recurring co-author surnames: {', '.join(shared[:5])}")
    if normalise_name(a.raw_name) in prof.confirmed_variant_norms:
        score += W_CONFIRMED_ALIAS
        ev["signals"].append("byline equals a researcher-confirmed name")
    score = round(min(score, 0.95), 3)

    if score >= HIGH:
        conf = MatchConfidence.HIGH
    elif score >= MEDIUM:
        conf = MatchConfidence.MEDIUM
    else:
        conf = MatchConfidence.LOW
    # Two bylines on one paper both fit the researcher's name: cannot be HIGH.
    if len(hits) > 1 and hits[1][1].score >= 0.6 and conf == MatchConfidence.HIGH:
        conf = MatchConfidence.MEDIUM
        ev["signals"].append("more than one byline on this paper fits the name")
    return MatchResult(conf, score, f"name:{nc.kind}", a, ev)
