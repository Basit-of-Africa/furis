"""ORCID public API: an independent discovery channel (§7.3).

ORCID works are researcher-claimed and carry no author list; the record owner is
the author. Absence from ORCID is *not* evidence of non-authorship.
Check ORCID public-API terms for the university's use before production (§21).
"""

from __future__ import annotations

from datetime import date

from furis.discovery.sources.base import Candidate, Query, QueryResult, Source
from furis.discovery.text import clean_text, normalise_doi

BASE = "https://pub.orcid.org/v3.0"


def _val(d: dict | None, *path: str):
    for p in path:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d


def parse_summary(s: dict, orcid: str) -> Candidate:
    doi = None
    for ext in _val(s, "external-ids", "external-id") or []:
        if (ext.get("external-id-type") or "").lower() == "doi":
            doi = normalise_doi(ext.get("external-id-value") or _val(ext, "external-id-normalized", "value"))
            if doi:
                break
    y = _val(s, "publication-date", "year", "value")
    m = _val(s, "publication-date", "month", "value")
    d = _val(s, "publication-date", "day", "value")
    year = int(y) if y and str(y).isdigit() else None
    pub_date = None
    if year and m and d:
        try:
            pub_date = date(year, int(m), int(d))
        except ValueError:
            pass
    put_code = s.get("put-code")
    return Candidate(
        source_name="orcid",
        source_record_id=f"{orcid}/{put_code}",
        source_url=f"https://orcid.org/{orcid}",
        title=clean_text(_val(s, "title", "title", "value")) or "",
        doi=doi,
        publication_year=year,
        publication_date=pub_date,
        document_type=(s.get("type") or "").lower() or None,
        journal_name=clean_text(_val(s, "journal-title", "value")),
        landing_page_url=_val(s, "url", "value"),
        owner_orcid=orcid,
        raw=s,
    )


class OrcidSource(Source):
    name = "orcid"

    def run(self, query: Query) -> QueryResult:
        if query.query_type != "orcid":
            raise ValueError(f"unsupported ORCID query type {query.query_type}")
        data = self.http.get_json(f"{BASE}/{query.value}/works", headers={"Accept": "application/json"})
        out = []
        for g in data.get("group") or []:
            summaries = g.get("work-summary") or []
            if summaries:
                # First summary is the researcher's preferred version of the grouped work.
                out.append(parse_summary(summaries[0], query.value))
        return self._collect(iter([(out, len(out))]))
