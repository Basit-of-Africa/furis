"""Common candidate representation and a polite HTTP client for all sources."""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date

import httpx

from furis.config import Settings


@dataclass
class CandidateAuthor:
    raw_name: str
    position: int
    orcid: str | None = None
    source_author_id: str | None = None
    raw_affiliations: list[str] = field(default_factory=list)
    institution_ids: list[str] = field(default_factory=list)  # OpenAlex IDs / RORs
    institution_names: list[str] = field(default_factory=list)


@dataclass
class Candidate:
    source_name: str
    source_record_id: str
    title: str
    doi: str | None = None
    source_url: str | None = None
    publication_year: int | None = None
    publication_date: date | None = None
    document_type: str | None = None
    journal_name: str | None = None
    publisher: str | None = None
    issn: str | None = None
    landing_page_url: str | None = None
    is_open_access: bool | None = None
    citation_count: int | None = None
    authors: list[CandidateAuthor] = field(default_factory=list)
    # ORCID works have no author list: the record owner *is* the author.
    owner_orcid: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class Query:
    source_name: str
    query_type: str  # e.g. orcid, openalex_author_id, raw_author_name, crossref_author
    value: str


@dataclass
class QueryResult:
    candidates: list[Candidate]
    records_found: int  # total reported by the source, where available
    truncated: bool = False


class SourceError(Exception):
    pass


class HttpClient:
    """httpx wrapper with retry/backoff on 429 and 5xx, honouring Retry-After."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None, min_interval: float = 0.11):
        ua = "FURIS/0.1 (Fountain University research information system)"
        if settings.contact_email:
            ua += f"; mailto:{settings.contact_email}"
        self.client = client or httpx.Client(
            timeout=settings.http_timeout_seconds, headers={"User-Agent": ua}, follow_redirects=True
        )
        self.max_retries = settings.http_max_retries
        self.min_interval = min_interval
        self._last = 0.0

    def get_json(self, url: str, params: dict | None = None, headers: dict | None = None) -> dict:
        for attempt in range(self.max_retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self.client.get(url, params=params, headers=headers)
            except httpx.TransportError as e:
                if attempt == self.max_retries:
                    raise SourceError(f"network error: {e}") from e
                time.sleep(2**attempt)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == self.max_retries:
                    raise SourceError(f"HTTP {r.status_code} from {url}")
                retry_after = r.headers.get("Retry-After", "")
                time.sleep(float(retry_after) if retry_after.isdigit() else 2**attempt)
                continue
            if r.status_code == 404:
                return {}
            if r.status_code >= 400:
                raise SourceError(f"HTTP {r.status_code} from {url}: {r.text[:200]}")
            return r.json()
        raise SourceError("retries exhausted")  # pragma: no cover


class Source:
    name: str = ""

    def __init__(self, http: HttpClient, settings: Settings):
        self.http = http
        self.settings = settings

    def supports(self, query: Query) -> bool:
        return query.source_name == self.name

    def run(self, query: Query) -> QueryResult:
        raise NotImplementedError

    def _collect(self, pages: Iterator[tuple[list[Candidate], int]]) -> QueryResult:
        cap = self.settings.max_records_per_query
        out: list[Candidate] = []
        total = 0
        for batch, reported in pages:
            total = max(total, reported)
            out.extend(batch)
            if len(out) >= cap:
                return QueryResult(out[:cap], total, truncated=total > cap)
        return QueryResult(out, max(total, len(out)))
