"""Crossref REST API: DOI-linked publisher metadata (§7.4).

`query.author` is a relevance search, not an exact filter, so results are broad;
the matching engine decides which byline (if any) is the researcher.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from furis.discovery.sources.base import Candidate, CandidateAuthor, Query, QueryResult, Source
from furis.discovery.text import clean_text, normalise_doi, normalise_orcid

BASE = "https://api.crossref.org"
SELECT = (
    "DOI,title,author,issued,published-online,published-print,type,container-title,"
    "publisher,URL,is-referenced-by-count,ISSN"
)
ROWS = 100


def _date(parts_obj: dict | None) -> tuple[int | None, date | None]:
    parts = ((parts_obj or {}).get("date-parts") or [[None]])[0]
    if not parts or parts[0] is None:
        return None, None
    y = int(parts[0])
    if len(parts) >= 3:
        try:
            return y, date(y, int(parts[1]), int(parts[2]))
        except ValueError:
            pass
    return y, None


def parse_item(it: dict) -> Candidate:
    # Prefer online publication date (earliest public availability), then print, then issued.
    year, pub_date = None, None
    for key in ("published-online", "published-print", "issued"):
        y, d = _date(it.get(key))
        if year is None and y:
            year = y
        if pub_date is None and d:
            pub_date = d
    authors = []
    for i, a in enumerate(it.get("author") or []):
        name = " ".join(p for p in (a.get("given"), a.get("family")) if p) or a.get("name") or ""
        if a.get("family") and a.get("given"):
            name = f"{a['family']}, {a['given']}"  # unambiguous family name for parsing
        authors.append(
            CandidateAuthor(
                raw_name=name,
                position=i + 1,
                orcid=normalise_orcid(a.get("ORCID")),
                raw_affiliations=[af.get("name") for af in (a.get("affiliation") or []) if af.get("name")],
            )
        )
    doi = normalise_doi(it.get("DOI"))
    titles = it.get("title") or []
    containers = it.get("container-title") or []
    issns = it.get("ISSN") or []
    return Candidate(
        source_name="crossref",
        source_record_id=doi or "",
        source_url=f"https://doi.org/{doi}" if doi else None,
        title=clean_text(titles[0]) if titles else "",
        doi=doi,
        publication_year=year,
        publication_date=pub_date,
        document_type=it.get("type"),
        journal_name=clean_text(containers[0]) if containers else None,
        publisher=it.get("publisher"),
        issn=issns[0] if issns else None,
        landing_page_url=it.get("URL"),
        citation_count=it.get("is-referenced-by-count"),
        authors=authors,
        raw=it,
    )


class CrossrefSource(Source):
    name = "crossref"

    def _pages(self, q: Query) -> Iterator[tuple[list[Candidate], int]]:
        if q.query_type == "crossref_author":
            params = {"query.author": q.value, "rows": ROWS, "cursor": "*", "select": SELECT}
        elif q.query_type == "orcid":
            params = {"filter": f"orcid:{q.value}", "rows": ROWS, "cursor": "*", "select": SELECT}
        else:
            raise ValueError(f"unsupported Crossref query type {q.query_type}")
        if self.settings.contact_email:
            params["mailto"] = self.settings.contact_email
        while True:
            msg = self.http.get_json(f"{BASE}/works", params=params).get("message") or {}
            items = msg.get("items") or []
            yield [parse_item(i) for i in items if i.get("DOI")], msg.get("total-results") or 0
            if not items or not msg.get("next-cursor") or len(items) < ROWS:
                return
            params["cursor"] = msg["next-cursor"]

    def run(self, query: Query) -> QueryResult:
        return self._collect(self._pages(query))
