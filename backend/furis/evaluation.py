"""Evaluate discovery and matching against a ground-truth dataset (§17.3, §18).

Ground-truth CSV columns:
    staff_number, doi, title, is_author, is_fu_output
`is_author` is yes/no. A "no" row records a known false candidate (a negative).
`is_fu_output` is optional (yes/no/blank). Rows are keyed by DOI, else by normalised title.

Precision counts only predictions whose label is known. Predictions that are not in
the ground truth are reported separately as `unlabelled` instead of being guessed.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from furis.discovery.text import normalise_doi, normalise_title
from furis.models import (
    AttributionStatus,
    IdentityMatch,
    InstitutionalAttribution,
    MatchConfidence,
    Publication,
    Researcher,
)

LEVELS = {
    "high": {MatchConfidence.HIGH},
    "medium": {MatchConfidence.HIGH, MatchConfidence.MEDIUM},
    "low": {MatchConfidence.HIGH, MatchConfidence.MEDIUM, MatchConfidence.LOW},
}


def _key(doi: str | None, title: str | None) -> str | None:
    d = normalise_doi(doi)
    if d:
        return f"doi:{d}"
    t = normalise_title(title)
    return f"title:{t}" if t else None


def _yes(v: str | None) -> bool | None:
    v = (v or "").strip().lower()
    if v in {"yes", "y", "true", "1"}:
        return True
    if v in {"no", "n", "false", "0"}:
        return False
    return None


@dataclass
class Metrics:
    level: str
    positives: int
    predicted: int
    true_positive: int
    false_positive: int
    unlabelled: int
    false_negative: int
    precision: float | None
    recall: float | None
    f1: float | None
    discovery_coverage: float | None  # known pubs found at any confidence (incl. rejected)
    attribution_labelled: int
    attribution_accuracy: float | None
    false_attribution_rate: float | None


def evaluate(db: Session, csv_path: str, level: str = "medium") -> Metrics:
    truth: dict[tuple, bool] = {}
    fu_truth: dict[tuple, bool] = {}
    staff = {r.staff_number: r.id for r in db.scalars(select(Researcher)) if r.staff_number}
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            rid = staff.get((row.get("staff_number") or "").strip())
            k = _key(row.get("doi"), row.get("title"))
            label = _yes(row.get("is_author"))
            if rid is None or k is None or label is None:
                continue
            truth[(rid, k)] = label
            fu = _yes(row.get("is_fu_output"))
            if fu is not None:
                fu_truth[(rid, k)] = fu

    researchers = {rid for rid, _ in truth}
    found_any: set[tuple] = set()
    predicted: dict[tuple, MatchConfidence] = {}
    rows = db.execute(
        select(IdentityMatch, Publication).join(Publication, Publication.id == IdentityMatch.publication_id)
        .where(IdentityMatch.researcher_id.in_(researchers))
    )
    keys_by_pub: dict = defaultdict(set)
    for im, pub in rows:
        ks = {k for k in (_key(pub.doi, None), _key(None, pub.title)) if k}
        keys_by_pub[(im.researcher_id, pub.id)] = ks
        for k in ks:
            found_any.add((im.researcher_id, k))
            if im.confidence in LEVELS[level]:
                predicted[(im.researcher_id, k)] = im.confidence

    # Collapse DOI/title double keys so one publication counts once.
    pred_pubs = [(rid, ks) for (rid, _), ks in keys_by_pub.items() if any((rid, k) in predicted for k in ks)]
    tp = fp = unl = 0
    for rid, ks in pred_pubs:
        labels = [truth[(rid, k)] for k in ks if (rid, k) in truth]
        if not labels:
            unl += 1
        elif any(labels):
            tp += 1
        else:
            fp += 1
    positives = [k for k, v in truth.items() if v]
    hit_pos = sum(1 for k in positives if k in predicted)
    found_pos = sum(1 for k in positives if k in found_any)
    fn = len(positives) - hit_pos

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = hit_pos / len(positives) if positives else None
    f1 = (2 * precision * recall / (precision + recall)) if precision and recall else None

    # Attribution: system counts as FU output only if a reviewer confirmed it.
    att_ok = att_n = false_attr = counted_fu = 0
    for ia, pub in db.execute(
        select(InstitutionalAttribution, Publication).join(Publication, Publication.id == InstitutionalAttribution.publication_id)
        .where(InstitutionalAttribution.researcher_id.in_(researchers))
    ):
        ks = {k for k in (_key(pub.doi, None), _key(None, pub.title)) if k}
        labels = [fu_truth[(ia.researcher_id, k)] for k in ks if (ia.researcher_id, k) in fu_truth]
        if not labels:
            continue
        actual = any(labels)
        status = ia.final_status or ia.suggested_status
        said_fu = status in (AttributionStatus.CONFIRMED_FU_OUTPUT, AttributionStatus.POTENTIAL_FU_OUTPUT)
        att_n += 1
        att_ok += said_fu == actual
        if ia.final_status == AttributionStatus.CONFIRMED_FU_OUTPUT:
            counted_fu += 1
            false_attr += not actual

    return Metrics(
        level=level, positives=len(positives), predicted=len(pred_pubs), true_positive=tp, false_positive=fp,
        unlabelled=unl, false_negative=fn, precision=precision, recall=recall, f1=f1,
        discovery_coverage=found_pos / len(positives) if positives else None,
        attribution_labelled=att_n, attribution_accuracy=att_ok / att_n if att_n else None,
        false_attribution_rate=false_attr / counted_fu if counted_fu else None,
    )


def metrics_dict(m: Metrics) -> dict:
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in asdict(m).items()}
