from datetime import date

from furis.discovery.attribution import FuDetector, Period, assess
from furis.discovery.matching import ResearcherProfile, match_candidate
from furis.discovery.sources.base import Candidate, CandidateAuthor
from furis.models import AttributionStatus, MatchConfidence

ORCID = "0000-0002-1825-0097"


def prof(**kw):
    return ResearcherProfile(id=1, first="Abdul", middle="Basit", last="Ajibade", **kw)


def cand(*authors, **kw):
    return Candidate(source_name="openalex", source_record_id="W1", title="T", authors=list(authors), **kw)


FU_AFF = ["Department of Microbiology, Fountain University, Osogbo, Nigeria"]


def test_verified_orcid_is_deterministic(settings):
    fu = FuDetector(settings)
    m = match_candidate(cand(CandidateAuthor("A. B. Ajibade", 2, orcid=ORCID)), prof(verified_orcids={ORCID}), fu)
    assert m.confidence == MatchConfidence.HIGH and m.method == "orcid" and m.author.position == 2


def test_identifier_with_inconsistent_name_is_downgraded(settings):
    m = match_candidate(cand(CandidateAuthor("Kemi Adeyemi", 1, orcid=ORCID)), prof(verified_orcids={ORCID}),
                        FuDetector(settings))
    assert m.confidence == MatchConfidence.MEDIUM and m.evidence["warning"] == "identifier_name_inconsistency"


def test_different_orcid_on_byline_is_rejected(settings):
    m = match_candidate(cand(CandidateAuthor("Abdul Basit Ajibade", 1, orcid="0000-0001-5109-3700")),
                        prof(verified_orcids={ORCID}), FuDetector(settings))
    assert m.confidence == MatchConfidence.REJECTED


def test_name_plus_fu_affiliation_is_high(settings):
    m = match_candidate(cand(CandidateAuthor("Abdul Basit Ajibade", 1, raw_affiliations=FU_AFF)), prof(),
                        FuDetector(settings))
    assert m.confidence == MatchConfidence.HIGH


def test_name_alone_is_only_medium(settings):
    m = match_candidate(cand(CandidateAuthor("Abdul Basit Ajibade", 1)), prof(), FuDetector(settings))
    assert m.confidence == MatchConfidence.MEDIUM


def test_initials_alone_are_low(settings):
    m = match_candidate(cand(CandidateAuthor("A. Ajibade", 1)), prof(), FuDetector(settings))
    assert m.confidence == MatchConfidence.LOW


def test_raw_name_search_false_positive_is_ignored(settings):
    # raw_author_name.search can hit "Abdul" and "Ajibade" on different authors (§7.5).
    c = cand(CandidateAuthor("Abdul Rahman Bello", 1), CandidateAuthor("Kemi Ajibade", 2))
    assert match_candidate(c, prof(), FuDetector(settings)) is None


def test_two_fitting_bylines_cap_at_medium(settings):
    c = cand(CandidateAuthor("Abdul Basit Ajibade", 1, raw_affiliations=FU_AFF),
             CandidateAuthor("A. B. Ajibade", 3, raw_affiliations=FU_AFF))
    m = match_candidate(c, prof(), FuDetector(settings))
    assert m.confidence == MatchConfidence.MEDIUM


def test_fu_detection(settings):
    fu = FuDetector(settings)
    assert fu.text_is_fu("Fountain Univ., Osogbo")
    assert fu.text_is_fu("Dept of Chemistry, Fountain Unversity Oshogbo")
    assert not fu.text_is_fu("University of Ilorin")
    assert fu.author_is_fu(CandidateAuthor("x", 1, institution_ids=["I999FU"]))


FU_2024 = [Period(date(2024, 1, 15), None, True)]


def _assess(**kw):
    base = dict(pub_date=None, pub_year=None, has_fu_affiliation=False, other_affiliations=[],
                has_affiliation_data=False, periods=FU_2024)
    return assess(**(base | kw))[0]


def test_attribution_rules():
    A = AttributionStatus
    assert _assess(pub_date=date(2025, 3, 1), has_fu_affiliation=True, has_affiliation_data=True) == A.POTENTIAL_FU_OUTPUT
    # Brief's example: published 2021, joined 2024 → not FU output.
    assert _assess(pub_year=2021) == A.NOT_ATTRIBUTABLE
    # FU affiliation but before employment: conflicting, so review.
    assert _assess(pub_year=2021, has_fu_affiliation=True) == A.UNDER_REVIEW
    # During employment without FU in metadata: never auto-excluded (§9.4).
    assert _assess(pub_date=date(2025, 1, 1), other_affiliations=["Univ of Ibadan"],
                   has_affiliation_data=True) == A.UNDER_REVIEW
    # Year-only on the joining year is ambiguous.
    assert _assess(pub_year=2024, has_fu_affiliation=True) == A.UNDER_REVIEW
    assert assess(pub_date=date(2025, 1, 1), pub_year=2025, has_fu_affiliation=True, other_affiliations=[],
                  has_affiliation_data=True, periods=[])[0] == A.UNDER_REVIEW
    # Never auto-confirmed.
    assert A.CONFIRMED_FU_OUTPUT not in {
        _assess(pub_date=date(2025, 3, 1), has_fu_affiliation=True), _assess(pub_year=2026, has_fu_affiliation=True)}
