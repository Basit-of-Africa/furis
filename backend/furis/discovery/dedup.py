"""Canonical publication resolution (§10.1).

Automatic merge only on: exact (normalised) DOI, or exact normalised title + year
with an overlapping author surname and no conflicting DOIs. Fuzzy title matches
are *flagged* as duplicate candidates for review, never merged silently.
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from furis.discovery.matching import _surname
from furis.discovery.sources.base import Candidate
from furis.discovery.text import normalise_title
from furis.models import Publication, PublicationAuthor

FUZZY_FLAG = 92.0
MIN_TITLE_LEN_FOR_TITLE_MERGE = 20  # "Editorial", "Introduction"… never merge on title


@dataclass
class Resolution:
    publication: Publication | None
    method: str | None  # doi | title_year | None
    possible_duplicates: list[tuple[Publication, float]]


def _surnames(names: list[str]) -> set[str]:
    return {s for s in (_surname(n) for n in names) if s}


def resolve(db: Session, c: Candidate) -> Resolution:
    if c.doi:
        pub = db.scalar(select(Publication).where(Publication.doi == c.doi))
        if pub:
            return Resolution(pub, "doi", [])

    nt = normalise_title(c.title)
    if not nt:
        return Resolution(None, None, [])
    years = [c.publication_year + d for d in (-1, 0, 1)] if c.publication_year else [None]
    q = select(Publication)
    q = q.where(Publication.publication_year.in_(years)) if years != [None] else q.where(
        Publication.normalised_title == nt
    )
    cand_surnames = _surnames([a.raw_name for a in c.authors])
    possible: list[tuple[Publication, float]] = []
    for pub in db.scalars(q):
        if pub.doi and c.doi and pub.doi != c.doi:
            # Different DOIs: preprint vs article, erratum, etc. Flag only.
            sim = fuzz.token_sort_ratio(nt, pub.normalised_title)
            if sim >= FUZZY_FLAG:
                possible.append((pub, sim))
            continue
        if pub.normalised_title == nt and pub.publication_year == c.publication_year:
            existing = _surnames(
                [a.raw_author_name for a in db.scalars(
                    select(PublicationAuthor).where(PublicationAuthor.publication_id == pub.id)
                )]
            )
            overlap = not cand_surnames or not existing or bool(cand_surnames & existing)
            if len(nt) >= MIN_TITLE_LEN_FOR_TITLE_MERGE and overlap:
                return Resolution(pub, "title_year", [])
            possible.append((pub, 100.0))
            continue
        sim = fuzz.token_sort_ratio(nt, pub.normalised_title)
        if sim >= FUZZY_FLAG:
            possible.append((pub, sim))
    return Resolution(None, None, possible)
