"""CSV staff import (Module 1).

Columns (header row required):
    staff_number, first_name, middle_name, last_name, email, faculty, department,
    employment_start, employment_end, employment_type, orcid
`orcid` is stored *unverified*: only verified ORCIDs drive deterministic matching.
Re-importing is idempotent on staff_number.
"""

from __future__ import annotations

import csv
import io
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from furis.discovery.engine import ensure_system_variants
from furis.discovery.text import normalise_orcid
from furis.models import (
    Department,
    EmploymentHistory,
    Faculty,
    IdentifierType,
    Researcher,
    ResearcherIdentifier,
)

FU_NAME = "Fountain University, Osogbo"


def _d(v: str | None) -> date | None:
    v = (v or "").strip()
    return date.fromisoformat(v) if v else None


def _faculty(db: Session, name: str | None) -> Faculty | None:
    if not name:
        return None
    f = db.scalar(select(Faculty).where(Faculty.name == name))
    if not f:
        f = Faculty(name=name)
        db.add(f)
        db.flush()
    return f


def _department(db: Session, fac: Faculty | None, name: str | None) -> Department | None:
    if not name or not fac:
        return None
    d = db.scalar(select(Department).where(Department.faculty_id == fac.id, Department.name == name))
    if not d:
        d = Department(faculty_id=fac.id, name=name)
        db.add(d)
        db.flush()
    return d


def import_staff_csv(db: Session, text: str) -> dict:
    created = updated = 0
    errors: list[str] = []
    for i, row in enumerate(csv.DictReader(io.StringIO(text)), start=2):
        row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
        if not row.get("first_name") or not row.get("last_name"):
            errors.append(f"line {i}: first_name and last_name are required")
            continue
        try:
            start, end = _d(row.get("employment_start")), _d(row.get("employment_end"))
        except ValueError:
            errors.append(f"line {i}: dates must be YYYY-MM-DD")
            continue
        fac = _faculty(db, row.get("faculty"))
        dep = _department(db, fac, row.get("department"))
        sn = row.get("staff_number") or None
        r = db.scalar(select(Researcher).where(Researcher.staff_number == sn)) if sn else None
        if r is None:
            r = Researcher(staff_number=sn, first_name=row["first_name"], last_name=row["last_name"])
            db.add(r)
            created += 1
        else:
            updated += 1
        r.first_name, r.last_name = row["first_name"], row["last_name"]
        r.middle_name = row.get("middle_name") or None
        r.email = row.get("email") or r.email
        r.faculty_id = fac.id if fac else r.faculty_id
        r.department_id = dep.id if dep else r.department_id
        db.flush()

        if start and not any(e.is_fountain_university and e.start_date == start for e in r.employment):
            r.employment.append(EmploymentHistory(
                institution_name=FU_NAME, is_fountain_university=True, start_date=start, end_date=end,
                faculty_id=r.faculty_id, department_id=r.department_id,
                employment_type=row.get("employment_type") or None, evidence_reference="staff CSV import"))
        orcid = normalise_orcid(row.get("orcid"))
        if orcid and not db.scalar(select(ResearcherIdentifier).where(
                ResearcherIdentifier.identifier_type == IdentifierType.ORCID,
                ResearcherIdentifier.identifier_value == orcid)):
            r.identifiers.append(ResearcherIdentifier(identifier_type=IdentifierType.ORCID, identifier_value=orcid))
        ensure_system_variants(db, r)
    db.commit()
    return {"created": created, "updated": updated, "errors": errors}
