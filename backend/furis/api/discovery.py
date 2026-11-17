from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from furis import schemas as s
from furis.api.deps import audit, current_user, get_researcher_for, require_admin
from furis.db import SessionLocal, get_db
from furis.discovery.engine import DiscoveryEngine
from furis.models import SearchRun, User

router = APIRouter(prefix="/discovery", tags=["discovery"])
log = logging.getLogger(__name__)


def _run(researcher_id: uuid.UUID) -> None:
    # Own session: the request's session closes when the response is sent.
    # For production, move this to a proper worker/queue (§11.3).
    with SessionLocal() as db:
        try:
            DiscoveryEngine(db).run_for_researcher(researcher_id)
        except Exception:  # logged; per-query failures are already on search_runs
            log.exception("discovery job failed for %s", researcher_id)


@router.post("/researchers/{researcher_id}", status_code=202)
def start_discovery(researcher_id: uuid.UUID, tasks: BackgroundTasks, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    r = get_researcher_for(db, user, researcher_id)
    audit(db, user, "start_discovery", "researcher", r.id)
    db.commit()
    tasks.add_task(_run, r.id)
    return {"status": "queued", "researcher_id": str(r.id)}


@router.get("/runs", response_model=list[s.SearchRunOut])
def list_runs(researcher_id: uuid.UUID, limit: int = 200, db: Session = Depends(get_db),
              user: User = Depends(current_user)):
    get_researcher_for(db, user, researcher_id)
    return db.scalars(select(SearchRun).where(SearchRun.researcher_id == researcher_id)
                      .order_by(SearchRun.started_at.desc()).limit(min(limit, 1000))).all()
