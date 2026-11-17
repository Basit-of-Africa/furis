"""Process discovery requests queued by the portal (serverless deployments)."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from furis.discovery.engine import DiscoveryEngine
from furis.models import DiscoveryRequest, RequestStatus, utcnow

log = logging.getLogger(__name__)
STALE_AFTER = timedelta(hours=3)  # a 'running' request older than this was interrupted


def process_pending(db: Session, engine: DiscoveryEngine, limit: int = 200) -> dict:
    # Requeue requests whose worker died mid-run.
    for req in db.scalars(select(DiscoveryRequest).where(
            DiscoveryRequest.status == RequestStatus.RUNNING, DiscoveryRequest.started_at < utcnow() - STALE_AFTER)):
        req.status, req.started_at = RequestStatus.PENDING, None
    db.commit()

    done = failed = 0
    reqs = list(db.scalars(select(DiscoveryRequest).where(DiscoveryRequest.status == RequestStatus.PENDING)
                          .order_by(DiscoveryRequest.requested_at).limit(limit)))
    for req in reqs:
        req.status, req.started_at = RequestStatus.RUNNING, utcnow()
        db.commit()
        try:
            summary = engine.run_for_researcher(req.researcher_id)
            if summary is not None and summary.queries and summary.failed == summary.queries:
                req.status = RequestStatus.FAILED
                req.error_message = "Every source query failed; see the search runs for details."
                failed += 1
            else:
                req.status = RequestStatus.DONE
                done += 1
        except Exception as e:  # recorded on the request; other requests continue
            db.rollback()
            req = db.merge(req)
            req.status, req.error_message = RequestStatus.FAILED, str(e)[:2000]
            failed += 1
            log.exception("discovery request %s failed", req.id)
        req.completed_at = utcnow()
        db.commit()
    return {"processed": len(reqs), "done": done, "failed": failed}
