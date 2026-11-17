import httpx
import respx

from furis.discovery.sources.base import HttpClient, Query
from furis.discovery.sources.crossref import parse_item
from furis.discovery.sources.openalex import OpenAlexSource, parse_work
from furis.discovery.sources.orcid import parse_summary

OA_WORK = {
    "id": "https://openalex.org/W123",
    "doi": "https://doi.org/10.5555/ABC",
    "title": "Antimicrobial activity of <i>Moringa</i> extracts",
    "publication_year": 2025,
    "publication_date": "2025-03-14",
    "type": "article",
    "primary_location": {"landing_page_url": "https://j.example/1",
                         "source": {"display_name": "J Ethnopharm", "host_organization_name": "Elsevier",
                                    "issn": ["0378-8741"]}},
    "authorships": [
        {"author": {"id": "https://openalex.org/A1", "display_name": "Kemi Bello", "orcid": None},
         "raw_author_name": "K. Bello", "raw_affiliation_strings": ["University of Ibadan"], "institutions": []},
        {"author": {"id": "https://openalex.org/A2", "display_name": "Abdul Basit Ajibade",
                    "orcid": "https://orcid.org/0000-0002-1825-0097"},
         "raw_author_name": "A. B. Ajibade",
         "raw_affiliation_strings": ["Fountain University, Osogbo"],
         "institutions": [{"id": "https://openalex.org/I999FU", "display_name": "Fountain University",
                           "ror": "https://ror.org/0fu"}]},
    ],
    "cited_by_count": 7,
    "open_access": {"is_oa": True},
}


def test_parse_openalex():
    c = parse_work(OA_WORK)
    assert c.doi == "10.5555/abc" and c.source_record_id == "W123"
    assert c.title == "Antimicrobial activity of Moringa extracts"
    a = c.authors[1]
    assert (a.raw_name, a.position, a.orcid, a.source_author_id) == ("A. B. Ajibade", 2, "0000-0002-1825-0097", "A2")
    assert "I999FU" in a.institution_ids and "0fu" in a.institution_ids
    assert c.journal_name == "J Ethnopharm" and c.is_open_access and c.citation_count == 7


def test_parse_crossref_prefers_online_date():
    c = parse_item({
        "DOI": "10.5555/ABC", "title": ["A title"], "type": "journal-article",
        "published-online": {"date-parts": [[2024, 12, 20]]}, "published-print": {"date-parts": [[2025, 2]]},
        "author": [{"given": "Abdul Basit", "family": "Ajibade", "ORCID": "http://orcid.org/0000-0002-1825-0097",
                    "affiliation": [{"name": "Fountain University"}]}],
        "container-title": ["J X"], "is-referenced-by-count": 3,
    })
    assert c.publication_year == 2024 and str(c.publication_date) == "2024-12-20"
    assert c.authors[0].raw_name == "Ajibade, Abdul Basit" and c.authors[0].raw_affiliations == ["Fountain University"]


def test_parse_orcid_summary():
    c = parse_summary({
        "put-code": 42, "title": {"title": {"value": "Paper"}}, "type": "JOURNAL_ARTICLE",
        "external-ids": {"external-id": [{"external-id-type": "doi", "external-id-value": "10.5555/XYZ"}]},
        "publication-date": {"year": {"value": "2023"}, "month": {"value": "05"}, "day": None},
    }, "0000-0002-1825-0097")
    assert c.doi == "10.5555/xyz" and c.publication_year == 2023 and c.owner_orcid == "0000-0002-1825-0097"
    assert c.source_record_id == "0000-0002-1825-0097/42"


@respx.mock
def test_openalex_paginates_and_retries(settings):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        cursor = request.url.params["cursor"]
        assert request.url.params["filter"] == "raw_author_name.search:Ajibade A. B."
        if cursor == "*":
            return httpx.Response(200, json={"meta": {"count": 2, "next_cursor": "c2"}, "results": [OA_WORK]})
        return httpx.Response(200, json={"meta": {"count": 2, "next_cursor": None},
                                         "results": [OA_WORK | {"id": "https://openalex.org/W124"}]})

    respx.get("https://api.openalex.org/works").mock(side_effect=handler)
    src = OpenAlexSource(HttpClient(settings, min_interval=0), settings)
    res = src.run(Query("openalex", "raw_author_name", "Ajibade, A. B."))
    assert [c.source_record_id for c in res.candidates] == ["W123", "W124"]
    assert res.records_found == 2 and not res.truncated
