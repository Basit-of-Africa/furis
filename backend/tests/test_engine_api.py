"""End-to-end: discovery with fake sources → review queue → decisions → analytics → evaluation."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from furis.db import get_db
from furis.discovery.engine import DiscoveryEngine
from furis.discovery.sources.base import Candidate, CandidateAuthor, Query, QueryResult, Source, SourceError
from furis.evaluation import evaluate
from furis.main import app
from furis.models import (
    AttributionStatus,
    DuplicateCandidate,
    EmploymentHistory,
    IdentifierType,
    IdentityMatch,
    InstitutionalAttribution,
    MatchConfidence,
    NameVariant,
    Publication,
    PublicationSource,
    Researcher,
    ResearcherIdentifier,
    RunStatus,
    SearchRun,
    User,
    UserRole,
    VariantType,
)

ORCID = "0000-0002-1825-0097"
FU = ["Fountain University, Osogbo, Nigeria"]


def _c(source, rid, title, doi=None, year=2025, d=None, authors=(), **kw):
    return Candidate(source_name=source, source_record_id=rid, title=title, doi=doi, publication_year=year,
                     publication_date=d, authors=list(authors), **kw)


class FakeSource(Source):
    def __init__(self, name, results, fail_types=()):
        self.name, self.results, self.fail_types, self.queries = name, results, set(fail_types), []

    def run(self, q: Query) -> QueryResult:
        self.queries.append(q)
        if q.query_type in self.fail_types:
            raise SourceError("HTTP 503 from fake")
        cands = self.results.get(q.query_type, [])
        return QueryResult(cands, len(cands))


@pytest.fixture
def world(db, settings):
    r = Researcher(staff_number="FU001", first_name="Abdul", middle_name="Basit", last_name="Ajibade")
    r.identifiers.append(ResearcherIdentifier(identifier_type=IdentifierType.ORCID, identifier_value=ORCID,
                                              verified=True))
    r.employment.append(EmploymentHistory(institution_name="Fountain University", start_date=date(2024, 1, 15)))
    db.add(r)
    admin = User(email="ro@fuo.test", full_name="Research Office", role=UserRole.RESEARCH_OFFICE)
    db.add(admin)
    db.flush()
    db.add(User(email="abdul@fuo.test", full_name="Abdul", role=UserRole.RESEARCHER, researcher_id=r.id))
    db.add(User(email="other@fuo.test", full_name="Other", role=UserRole.RESEARCHER))
    db.commit()

    oa = FakeSource("openalex", {
        "orcid": [_c("openalex", "W1", "Antimicrobial activity of Moringa oleifera leaf extracts", doi="10.5555/a",
                     d=date(2025, 3, 1), authors=[CandidateAuthor("A. B. Ajibade", 1, orcid=ORCID, raw_affiliations=FU),
                                                  CandidateAuthor("K. Bello", 2)])],
        "raw_author_name": [
            # Pre-employment paper: authorship plausible, but not FU output.
            _c("openalex", "W2", "Soil microbial diversity in southwestern Nigeria", doi="10.5555/b", year=2021,
               authors=[CandidateAuthor("Abdul Basit Ajibade", 1, raw_affiliations=["University of Ilorin"])]),
            # Cross-author false positive from raw_author_name.search.
            _c("openalex", "W3", "Unrelated paper", authors=[CandidateAuthor("Abdul Bello", 1),
                                                              CandidateAuthor("Kemi Ajibade", 2)]),
            # Near-duplicate title without DOI → flagged, not merged.
            _c("openalex", "W4", "Antimicrobial activity of Moringa oleifera leaf extract", d=date(2025, 3, 1),
               authors=[CandidateAuthor("A. B. Ajibade", 1, raw_affiliations=FU)]),
        ],
    })
    cr = FakeSource("crossref", {
        # Same DOI as W1 → merged into one canonical record with two source records.
        "orcid": [_c("crossref", "10.5555/a", "Antimicrobial activity of Moringa oleifera leaf extracts",
                     doi="10.5555/a", authors=[CandidateAuthor("Ajibade, Abdul Basit", 1, orcid=ORCID)])],
    }, fail_types={"crossref_author"})
    orc = FakeSource("orcid", {"orcid": [_c("orcid", f"{ORCID}/1", "Antimicrobial activity of Moringa oleifera "
                                            "leaf extracts", doi="10.5555/A", owner_orcid=ORCID)]})
    return r, DiscoveryEngine(db, settings, sources=[oa, cr, orc]), oa


def test_discovery_pipeline(db, world):
    r, eng, oa = world
    summary = eng.run_for_researcher(r.id)
    assert summary.failed == 1  # crossref_author failed, logged, rest continued

    pubs = db.scalars(select(Publication)).all()
    titles = {p.title for p in pubs}
    assert "Unrelated paper" in titles  # ingested (provenance) …
    w3 = next(p for p in pubs if p.title == "Unrelated paper")
    assert db.scalar(select(IdentityMatch).where(IdentityMatch.publication_id == w3.id)) is None  # … but not matched

    w1 = db.scalar(select(Publication).where(Publication.doi == "10.5555/a"))
    assert {s.source_name for s in w1.sources} == {"openalex", "crossref", "orcid"}
    m1 = db.scalar(select(IdentityMatch).where(IdentityMatch.publication_id == w1.id))
    assert m1.confidence == MatchConfidence.HIGH and m1.match_status.value == "candidate"
    ia1 = db.scalar(select(InstitutionalAttribution).where(InstitutionalAttribution.publication_id == w1.id))
    assert ia1.suggested_status == AttributionStatus.POTENTIAL_FU_OUTPUT and ia1.final_status is None

    w2 = db.scalar(select(Publication).where(Publication.doi == "10.5555/b"))
    ia2 = db.scalar(select(InstitutionalAttribution).where(InstitutionalAttribution.publication_id == w2.id))
    assert ia2.suggested_status == AttributionStatus.NOT_ATTRIBUTABLE

    assert db.scalar(select(DuplicateCandidate)) is not None
    runs = db.scalars(select(SearchRun)).all()
    assert {r_.run_status for r_ in runs} == {RunStatus.COMPLETED, RunStatus.FAILED}
    # Identifier-backed byline became a pending discovered variant.
    assert db.scalar(select(NameVariant).where(NameVariant.variant_type == VariantType.DISCOVERED,
                                               NameVariant.normalised_name == "a b ajibade")) is None  # already generated
    # Name search used confirmed variants only, de-duplicated by token set.
    names = [q.value for q in oa.queries if q.query_type == "raw_author_name"]
    assert "Abdul Basit Ajibade" in names and "Ajibade, Abdul Basit" not in names

    # Idempotent re-run: no new publications or sources.
    n_src = len(db.scalars(select(PublicationSource)).all())
    assert eng.run_for_researcher(r.id).new_publications == 0
    assert len(db.scalars(select(PublicationSource)).all()) == n_src


@pytest.fixture
def client(Session):
    def _db():
        with Session() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    yield TestClient(app)
    app.dependency_overrides.clear()


def H(email):
    return {"X-User-Email": email}


def test_verification_flow(db, world, client, tmp_path):
    r, eng, _ = world
    eng.run_for_researcher(r.id)
    w1 = db.scalar(select(Publication).where(Publication.doi == "10.5555/a"))
    w2 = db.scalar(select(Publication).where(Publication.doi == "10.5555/b"))

    assert client.get("/verification/queue").status_code == 401
    q = client.get("/verification/queue", headers=H("abdul@fuo.test")).json()
    assert q[0]["match"]["confidence"] == "high"
    # Another researcher cannot see or decide this researcher's records.
    assert client.get("/verification/queue", headers=H("other@fuo.test")).json() == []
    body = {"publication_id": str(w1.id), "researcher_id": str(r.id), "decision": "confirmed"}
    assert client.post("/verification/authorship", json=body, headers=H("other@fuo.test")).status_code == 404

    # Researcher cannot approve attribution; RO cannot confirm FU output before authorship.
    att = {"publication_id": str(w1.id), "researcher_id": str(r.id), "status": "confirmed_fu_output",
           "evidence": "FU affiliation in Crossref and OpenAlex; published during employment"}
    assert client.post("/verification/attribution", json=att, headers=H("abdul@fuo.test")).status_code == 403
    assert client.post("/verification/attribution", json=att, headers=H("ro@fuo.test")).status_code == 409

    assert client.post("/verification/authorship", json=body, headers=H("abdul@fuo.test")).status_code == 200
    res = client.post("/verification/attribution", json=att, headers=H("ro@fuo.test"))
    assert res.status_code == 200 and res.json()["final_status"] == "confirmed_fu_output"

    # W2: researcher confirms authorship; RO marks it as theirs but not FU output.
    client.post("/verification/authorship", headers=H("abdul@fuo.test"),
                json={"publication_id": str(w2.id), "researcher_id": str(r.id), "decision": "confirmed"})
    client.post("/verification/attribution", headers=H("ro@fuo.test"),
                json={"publication_id": str(w2.id), "researcher_id": str(r.id),
                      "status": "researcher_publication_not_fu"})

    s = client.get("/analytics/summary", headers=H("ro@fuo.test")).json()
    assert s["confirmed_researcher_publications"] == 2 and s["confirmed_fu_output"] == 1
    assert s["fu_output_by_year"] == [{"year": 2025, "count": 1}]
    assert s["pct_researchers_verified_orcid"] == 100.0

    detail = client.get(f"/publications/{w1.id}", headers=H("abdul@fuo.test")).json()
    assert len(detail["sources"]) == 3
    assert any(a["researcher_id"] == str(r.id) for a in detail["authors"])
    assert len(client.get("/verification/history", params={"publication_id": str(w1.id)},
                          headers=H("ro@fuo.test")).json()) == 2

    # Evaluate against a ground-truth file.
    gt = tmp_path / "gt.csv"
    gt.write_text("staff_number,doi,title,is_author,is_fu_output\n"
                  "FU001,10.5555/a,,yes,yes\n"
                  "FU001,10.5555/b,,yes,no\n"
                  "FU001,10.5555/missing,,yes,yes\n")
    with eng.db as s2:
        m = evaluate(s2, str(gt), level="medium")
    assert m.positives == 3 and m.true_positive == 2 and m.false_positive == 0
    assert m.recall == pytest.approx(2 / 3) and m.precision == 1.0
    assert m.attribution_accuracy == 1.0 and m.false_attribution_rate == 0.0


def test_duplicate_merge(db, world, client):
    r, eng, _ = world
    eng.run_for_researcher(r.id)
    dup = db.scalar(select(DuplicateCandidate))
    res = client.post(f"/duplicates/{dup.id}", json={"status": "merged"}, headers=H("ro@fuo.test"))
    assert res.status_code == 200
    db.expire_all()
    w1 = db.scalar(select(Publication).where(Publication.doi == "10.5555/a"))
    assert {s.source_record_id for s in w1.sources} >= {"W1", "W4"}
    assert db.scalar(select(Publication).where(Publication.title.like("%leaf extract"))) is None


def test_staff_import(client, db):
    db.add(User(email="admin@fuo.test", full_name="A", role=UserRole.SUPER_ADMIN))
    db.commit()
    csv_text = ("staff_number,first_name,middle_name,last_name,email,faculty,department,employment_start,"
                "employment_end,employment_type,orcid\n"
                "FU100,Aisha,,Lawal,a@fuo.test,Natural Sciences,Microbiology,2019-10-01,,full-time,"
                "https://orcid.org/0000-0001-5109-3700\n"
                "FU101,,,Nobody,,,,,,,\n")
    res = client.post("/researchers/import", files={"file": ("s.csv", csv_text)}, headers=H("admin@fuo.test"))
    body = res.json()
    assert body["created"] == 1 and len(body["errors"]) == 1
    rid = client.get("/researchers", headers=H("admin@fuo.test")).json()[0]["id"]
    d = client.get(f"/researchers/{rid}", headers=H("admin@fuo.test")).json()
    assert d["identifiers"][0]["verified"] is False  # imported ORCIDs need verification
    assert any(v["variant_name"] == "A. Lawal" for v in d["name_variants"])
    assert d["employment"][0]["start_date"] == "2019-10-01"
