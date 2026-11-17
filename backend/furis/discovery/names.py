"""Name normalisation, variant generation (§7.2) and byline comparison (§8.2).

Comparison is deliberately conservative: a byline token that cannot be explained by
any registered given name is treated as a *conflict* (e.g. "Kemi Ajibade" vs
"Abdul Basit Ajibade") rather than a weaker match, because false attribution is
costlier than a missed match (§8.4).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from rapidfuzz import fuzz

_PARTICLES = {"dr", "prof", "mr", "mrs", "ms", "engr", "alhaji", "alhaja", "phd", "jr", "sr"}


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalise_name(s: str) -> str:
    """Lower-case, accent-free, punctuation collapsed to single spaces."""
    s = strip_accents(s).lower()
    s = re.sub(r"[^a-z\s,]", " ", s.replace("-", " ").replace(".", " "))
    return re.sub(r"\s+", " ", s.replace(",", " ")).strip()


@dataclass(frozen=True)
class ParsedName:
    given: tuple[str, ...]  # full given names and/or single-letter initials, in order
    family: str | None  # None when the byline order is ambiguous
    tokens: tuple[str, ...]  # all tokens, original order


def _split_initials(token: str) -> list[str]:
    # "A.B." -> ["a", "b"]; "AB" (all caps, ≤3 letters) -> ["a", "b"]
    letters = re.sub(r"[^A-Za-z]", "", token)
    if not letters:
        return []
    if re.fullmatch(r"([A-Za-z]\.)+[A-Za-z]?\.?", token) or (letters.isupper() and 1 < len(letters) <= 3):
        return [c.lower() for c in letters]
    return [strip_accents(letters).lower()]


def parse_byline(raw: str) -> ParsedName:
    raw = strip_accents(raw).strip()
    if "," in raw:  # "Ajibade, A. B." – family name is explicit
        family_part, _, given_part = raw.partition(",")
        family = normalise_name(family_part).replace(" ", "")
        given: list[str] = []
        for t in re.split(r"[\s\-]+", given_part.strip()):
            given.extend(_split_initials(t))
        given = [g for g in given if g not in _PARTICLES]
        return ParsedName(tuple(given), family or None, tuple(given) + ((family,) if family else ()))
    tokens: list[str] = []
    for t in re.split(r"[\s\-]+", raw):
        tokens.extend(_split_initials(t))
    tokens = [t for t in tokens if t and t not in _PARTICLES]
    return ParsedName(tuple(tokens), None, tuple(tokens))


def _registered_given(first: str, middle: str | None) -> list[str]:
    return normalise_name(" ".join(p for p in (first, middle) if p)).split()


def generate_variants(first: str, middle: str | None, last: str) -> list[str]:
    """Category 1 (system-generated) variants for a researcher."""
    given = [g.strip() for g in re.split(r"\s+", " ".join(p for p in (first, middle) if p).strip()) if g.strip()]
    last = last.strip()
    out: list[str] = []

    def add(v: str) -> None:
        v = re.sub(r"\s+", " ", v).strip()
        if v and v.lower() not in {o.lower() for o in out}:
            out.append(v)

    initials = ". ".join(g[0].upper() for g in given) + "." if given else ""
    add(" ".join(given + [last]))
    if len(given) > 1:
        add("".join(given) + " " + last)  # AbdulBasit Ajibade
        for g in given:
            add(f"{g} {last}")  # Abdul Ajibade, Basit Ajibade
    add(f"{initials} {last}")
    if given:
        add(f"{given[0][0].upper()}. {last}")
    add(f"{last}, {' '.join(given)}")
    add(f"{last}, {initials}")
    if len(given) > 1:
        for g in given[1:]:
            add(f"{last}, {g}")
    # Surname-first order without a comma is common in Nigerian bylines.
    add(f"{last} {' '.join(given)}")
    return out


@dataclass
class NameComparison:
    score: float  # 0..1
    kind: str  # exact | full_partial | initials | surname_only | conflict | no_surname
    detail: dict = field(default_factory=dict)


def _token_matches_given(tok: str, given: list[str], used: set[int]) -> int | None:
    """Return the index of the registered given name `tok` explains, or None."""
    for i, g in enumerate(given):
        if i in used:
            continue
        if len(tok) == 1:
            if g[0] == tok:
                return i
        elif tok == g or (len(tok) >= 4 and fuzz.ratio(tok, g) >= 88):
            return i
    return None


def compare(raw_byline: str, first: str, middle: str | None, last: str) -> NameComparison:
    """Compare a publication byline with a registered name."""
    given = _registered_given(first, middle)
    family = normalise_name(last).replace(" ", "")
    parsed = parse_byline(raw_byline)
    toks = list(parsed.tokens)
    if parsed.family is not None:
        fam_idx = len(toks) - 1 if fuzz.ratio(parsed.family, family) >= 90 else None
    else:
        cands = [i for i, t in enumerate(toks) if len(t) > 1 and fuzz.ratio(t, family) >= 90]
        # Prefer last position (Western order), else first (surname-first order).
        fam_idx = cands[-1] if cands else None
    if fam_idx is None:
        return NameComparison(0.0, "no_surname")

    rest = [t for i, t in enumerate(toks) if i != fam_idx]
    if not rest:
        return NameComparison(0.3, "surname_only")

    # Merge concatenated given names: "abdulbasit" == "abdul" + "basit".
    joined = "".join(given)
    used: set[int] = set()
    full_hits = initial_hits = 0
    unexplained: list[str] = []
    for tok in rest:
        if len(tok) > 1 and len(given) > 1 and fuzz.ratio(tok, joined) >= 90:
            used.update(range(len(given)))
            full_hits += len(given)
            continue
        idx = _token_matches_given(tok, given, used)
        if idx is None:
            unexplained.append(tok)
            continue
        used.add(idx)
        if len(tok) == 1:
            initial_hits += 1
        else:
            full_hits += 1

    detail = {"full": full_hits, "initials": initial_hits, "unexplained": unexplained}
    if unexplained:
        return NameComparison(0.0, "conflict", detail)
    if full_hits == len(given):
        return NameComparison(1.0, "exact", detail)
    if full_hits >= 1:
        return NameComparison(0.9, "full_partial", detail)
    # Initials only: more initials matching = less ambiguous.
    return NameComparison(0.75 if initial_hits >= 2 else 0.6, "initials", detail)


def best_comparison(raw_byline: str, names: list[tuple[str, str | None, str]]) -> NameComparison:
    """Best comparison across the registered name and confirmed aliases."""
    best = NameComparison(0.0, "no_surname")
    for first, middle, last in names:
        c = compare(raw_byline, first, middle, last)
        if c.score > best.score:
            best = c
    return best
