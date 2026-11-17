"""FURIS command line.

    python -m furis.cli import-staff staff.csv
    python -m furis.cli discover --researcher <uuid> | --all
    python -m furis.cli evaluate ground_truth.csv [--level high|medium|low]
    python -m furis.cli create-user email@fuo.edu.ng "Full Name" research_office
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid

from sqlalchemy import select

from furis.db import SessionLocal
from furis.models import Researcher, User, UserRole


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="furis")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("import-staff")
    s.add_argument("csv_path")
    s = sub.add_parser("discover")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--researcher")
    g.add_argument("--all", action="store_true")
    s = sub.add_parser("evaluate")
    s.add_argument("csv_path")
    s.add_argument("--level", choices=["high", "medium", "low"], default="medium")
    s = sub.add_parser("create-user")
    s.add_argument("email")
    s.add_argument("full_name")
    s.add_argument("role", choices=[r.value for r in UserRole])
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    with SessionLocal() as db:
        if args.cmd == "import-staff":
            from furis.staff_import import import_staff_csv

            with open(args.csv_path, encoding="utf-8-sig") as f:
                print(json.dumps(import_staff_csv(db, f.read()), indent=2))
        elif args.cmd == "discover":
            from furis.discovery.engine import DiscoveryEngine

            ids = ([uuid.UUID(args.researcher)] if args.researcher else
                   list(db.scalars(select(Researcher.id).where(Researcher.archived_at.is_(None)))))
            eng = DiscoveryEngine(db)
            for rid in ids:
                s_ = eng.run_for_researcher(rid)
                print(f"{rid}: {s_.queries} queries, {s_.failed} failed, "
                      f"{s_.new_publications} new publications, {s_.matches} candidate matches")
        elif args.cmd == "evaluate":
            from furis.evaluation import evaluate, metrics_dict

            print(json.dumps(metrics_dict(evaluate(db, args.csv_path, args.level)), indent=2))
        elif args.cmd == "create-user":
            db.add(User(email=args.email.lower(), full_name=args.full_name, role=UserRole(args.role)))
            db.commit()
            print("created")
    return 0


if __name__ == "__main__":
    sys.exit(main())
