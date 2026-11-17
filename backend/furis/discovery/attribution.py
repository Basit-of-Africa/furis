"""Institutional attribution assessment (§9).

The engine only *suggests* a status. `confirmed_fu_output` is never assigned
automatically: it is set by an authorised Research Office reviewer, and only once
authorship has been confirmed (see api/verification.py).

POLICY_VERSION "draft-0" encodes the conservative defaults below. Replace these
rules with the Research Office's approved attribution policy (§9.5) and bump the
version, so every stored assessment records which rules produced it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from rapidfuzz import fuzz

from furis.config import Settings
from furis.models import AttributionStatus

POLICY_VERSION = "draft-0"

_FU_RE = re.compile(r"fountain\s*univ", re.IGNORECASE)


class FuDetector:
    def __init__(self, settings: Settings):
        self.ids = {i.rsplit("/", 1)[-1].lower() for i in settings.fu_openalex_institution_ids + settings.fu_ror_ids}

    def text_is_fu(self, raw: str) -> bool:
        if _FU_RE.search(raw):
            return True
        low = raw.lower()
        # Tolerate misspellings ("Fountain Unversity") but require "fountain".
        return "fountain" in low and fuzz.partial_ratio("fountain university", low) >= 90

    def author_is_fu(self, author) -> bool:
        if any(i.lower() in self.ids for i in author.institution_ids):
            return True
        return any(self.text_is_fu(s) for s in author.raw_affiliations + author.institution_names)


@dataclass
class Period:
    start: date | None
    end: date | None  # None = ongoing
    is_fu: bool


def _position(pub_date: date | None, year: int | None, p: Period) -> str:
    """'inside' | 'outside' | 'boundary' (year-only on a boundary year) | 'unknown'."""
    if p.start is None:
        return "unknown"
    if pub_date:
        if pub_date < p.start or (p.end and pub_date > p.end):
            return "outside"
        return "inside"
    if year is None:
        return "unknown"
    end_year = p.end.year if p.end else 9999
    if year < p.start.year or year > end_year:
        return "outside"
    if year == p.start.year or year == end_year:
        return "boundary"
    return "inside"


def assess(
    *,
    pub_date: date | None,
    pub_year: int | None,
    has_fu_affiliation: bool,
    other_affiliations: list[str],
    has_affiliation_data: bool,
    periods: list[Period],
) -> tuple[AttributionStatus, dict]:
    fu_periods = [p for p in periods if p.is_fu]
    positions = [_position(pub_date, pub_year, p) for p in fu_periods]
    ev = {
        "policy_version": POLICY_VERSION,
        "publication_date": pub_date.isoformat() if pub_date else None,
        "publication_year": pub_year,
        "fu_affiliation_in_metadata": has_fu_affiliation,
        "other_affiliations": other_affiliations[:5],
        "employment_positions": positions,
        "reasons": [],
    }
    r = ev["reasons"]

    if not fu_periods:
        r.append("no Fountain University employment period recorded")
        return AttributionStatus.UNDER_REVIEW, ev
    if "inside" in positions:
        when = "inside"
    elif "boundary" in positions or "unknown" in positions:
        when = "uncertain"
    else:
        when = "outside"

    if has_fu_affiliation and when == "inside":
        r.append("FU affiliation in metadata and published during FU employment")
        return AttributionStatus.POTENTIAL_FU_OUTPUT, ev
    if has_fu_affiliation:
        r.append(f"FU affiliation in metadata but publication date is {when} FU employment")
        return AttributionStatus.UNDER_REVIEW, ev
    if when == "outside":
        r.append("no FU affiliation and published outside FU employment")
        return AttributionStatus.NOT_ATTRIBUTABLE, ev
    if when == "inside" and other_affiliations:
        r.append("published during FU employment but metadata lists only other institutions")
    elif when == "inside" and not has_affiliation_data:
        r.append("published during FU employment; source has no affiliation data")
    else:
        r.append("publication date or affiliation evidence is incomplete")
    return AttributionStatus.UNDER_REVIEW, ev
