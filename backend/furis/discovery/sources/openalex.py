"""OpenAlex: primary discovery source (§7.4).

Query types:
- orcid               works filtered by author ORCID
- openalex_author_id  works filtered by a confirmed OpenAlex author ID
- raw_author_name     works whose bylines contain the variant (raw_author_name.search)

raw_author_name.search can match words spread across *different* authors on the
same paper (§7.5). Nothing here assumes a hit is a match: every authorship is kept
and the matching engine inspects each one.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from furis.discovery.sources.base import Candidate, CandidateAuthor, Query, QueryResult, Source
from furis.discovery.text import clean_text, normalise_doi, normalise_orcid

BASE = "https://api.openalex.org"
SELECT = (
    "id,doi,title,display_name,publication_year,publication_date,type,primary_location,"
    "authorships,cited_by_count,open_access"
)


def _short_id(url: str | None) -> str | None:
    return url.rsplit("/", 1)[-1] if url else None


def parse_work(w: dict) -> Candidate:
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    authors = []
    for i, a in enumerate(w.get("authorships") or []):
        au = a.get("author") or {}
        insts = a.get("institutions") or []
        authors.append(
            CandidateAuthor(
                raw_name=a.get("raw_author_name") or au.get("display_name") or "",
                position=i + 1,
                orcid=normalise_orcid(au.get("orcid")),
                source_author_id=_short_id(au.get("id")),
                raw_affiliations=[s for s in (a.get("raw_affiliation_strings") or []) if s],
                institution_ids=[x for i_ in insts for x in (_short_id(i_.get("id")), _short_id(i_.get("ror"))) if x],
                institution_names=[i_.get("display_name") for i_ in insts if i_.get("display_name")],
            )
        )
    pub_date = None
    if w.get("publication_date"):
        try:
            pub_date = date.fromisoformat(w["publication_date"])
        except ValueError:
            pass
    issns = src.get("issn") or []
    return Candidate(
        source_name="openalex",
        source_record_id=_short_id(w.get("id")) or "",
        source_url=w.get("id"),
        title=clean_text(w.get("title") or w.get("display_name")) or "",
        doi=normalise_doi(w.get("doi")),
        publication_year=w.get("publication_year"),
        publication_date=pub_date,
        document_type=w.get("type"),
        journal_name=src.get("display_name"),
        publisher=src.get("host_organization_name"),
        issn=issns[0] if issns else None,
        landing_page_url=loc.get("landing_page_url"),
        is_open_access=(w.get("open_access") or {}).get("is_oa"),
        citation_count=w.get("cited_by_count"),
        authors=authors,
        raw=w,
    )


class OpenAlexSource(Source):
    name = "openalex"

    def _params(self) -> dict:
        p: dict = {"select": SELECT, "per-page": 200}
        if self.settings.openalex_api_key:
            p["api_key"] = self.settings.openalex_api_key
        if self.settings.contact_email:
            p["mailto"] = self.settings.contact_email
        return p

    def _filter(self, q: Query) -> str:
        if q.query_type == "orcid":
            return f"author.orcid:{q.value}"
        if q.query_type == "openalex_author_id":
            return f"author.id:{q.value}"
        if q.query_type == "raw_author_name":
            # Commas and pipes are filter syntax in OpenAlex; strip them from names.
            v = q.value.replace(",", " ").replace("|", " ")
            return f"raw_author_name.search:{' '.join(v.split())}"
        raise ValueError(f"unsupported OpenAlex query type {q.query_type}")

    def _pages(self, q: Query) -> Iterator[tuple[list[Candidate], int]]:
        params = self._params() | {"filter": self._filter(q), "cursor": "*"}
        while True:
            data = self.http.get_json(f"{BASE}/works", params=params)
            results = data.get("results") or []
            yield [parse_work(w) for w in results], (data.get("meta") or {}).get("count") or 0
            nxt = (data.get("meta") or {}).get("next_cursor")
            if not results or not nxt:
                return
            params["cursor"] = nxt

    def run(self, query: Query) -> QueryResult:
        return self._collect(self._pages(query))

    def search_authors(self, name: str, limit: int = 10) -> list[dict]:
        """Possible OpenAlex author identities for a name. For human review only;
        never treated as a confirmed identifier (§7.5 step 4, §8.1)."""
        params = {k: v for k, v in self._params().items() if k != "select"}
        params |= {"search": name, "per-page": limit}
        data = self.http.get_json(f"{BASE}/authors", params=params)
        out = []
        for a in data.get("results") or []:
            insts = a.get("last_known_institutions") or []
            out.append(
                {
                    "openalex_id": _short_id(a.get("id")),
                    "display_name": a.get("display_name"),
                    "orcid": normalise_orcid(a.get("orcid")),
                    "works_count": a.get("works_count"),
                    "last_known_institutions": [i.get("display_name") for i in insts],
                }
            )
        return out
