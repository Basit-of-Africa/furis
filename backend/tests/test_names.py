import pytest

from furis.discovery.names import compare, generate_variants, normalise_name
from furis.discovery.text import normalise_doi, normalise_orcid, normalise_title

REG = ("Abdul", "Basit", "Ajibade")


def test_variants_cover_brief_examples():
    v = generate_variants(*REG)
    for expected in ["Abdul Basit Ajibade", "AbdulBasit Ajibade", "Abdul Ajibade", "Basit Ajibade",
                     "A. B. Ajibade", "A. Ajibade", "Ajibade, Abdul Basit", "Ajibade, A. B.", "Ajibade, Basit"]:
        assert expected in v
    assert len(v) == len({x.lower() for x in v})


@pytest.mark.parametrize("byline,kind", [
    ("Abdul Basit Ajibade", "exact"),
    ("AbdulBasit Ajibade", "exact"),
    ("Abdul-Basit Ajibade", "exact"),
    ("Ajibade, Abdul Basit", "exact"),
    ("AJIBADE Abdul Basit", "exact"),  # surname-first without comma
    ("Àbdul Básit Ajíbádé", "exact"),  # diacritics
    ("Basit Ajibade", "full_partial"),
    ("A. B. Ajibade", "initials"),
    ("Ajibade AB", "initials"),
    ("Ajibade, A.B.", "initials"),
    ("A. Ajibade", "initials"),
    ("Ajibade", "surname_only"),
    ("Kemi Ajibade", "conflict"),  # different given name: not a weak match
    ("A. K. Ajibade", "conflict"),  # unexplained initial
    ("Abdul Basit Adeyemi", "no_surname"),
])
def test_compare_kinds(byline, kind):
    assert compare(byline, *REG).kind == kind


def test_compare_scores_are_ordered():
    s = lambda b: compare(b, *REG).score
    assert s("Abdul Basit Ajibade") > s("Basit Ajibade") > s("A. B. Ajibade") > s("A. Ajibade") > s("Ajibade") > 0
    assert s("Kemi Ajibade") == 0


def test_normalisers():
    assert normalise_name("Ajibade, A.-B.") == "ajibade a b"
    assert normalise_doi("https://doi.org/10.1234/ABC.def.") == "10.1234/abc.def"
    assert normalise_doi("not a doi") is None
    assert normalise_orcid("https://orcid.org/0000-0002-1825-009x") == "0000-0002-1825-009X"
    assert normalise_title("<i>Malaria</i> in Osun:  a <b>review</b>!") == "malaria in osun a review"
