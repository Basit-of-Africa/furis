import html
import re
import unicodedata

_DOI_RE = re.compile(r"10\.\d{4,9}/\S+", re.IGNORECASE)


def normalise_doi(value: str | None) -> str | None:
    if not value:
        return None
    m = _DOI_RE.search(value.strip())
    if not m:
        return None
    return m.group(0).rstrip(".,;)").lower()


def normalise_title(title: str | None) -> str:
    if not title:
        return ""
    t = html.unescape(title)
    t = re.sub(r"<[^>]+>", " ", t)  # Crossref titles can carry JATS/MathML tags
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def clean_text(value: str | None) -> str | None:
    """Strip markup from external metadata before storage (§21: untrusted input)."""
    if value is None:
        return None
    v = re.sub(r"<[^>]+>", " ", html.unescape(value))
    return re.sub(r"\s+", " ", v).strip() or None


def normalise_orcid(value: str | None) -> str | None:
    if not value:
        return None
    m = re.search(r"(\d{4}-\d{4}-\d{4}-\d{3}[\dX])", value.upper())
    return m.group(1) if m else None
