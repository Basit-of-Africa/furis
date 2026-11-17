"""Ask GitHub Actions to run the discovery workflow now (serverless deployments)."""

from __future__ import annotations

import logging

import httpx

from furis.config import Settings

log = logging.getLogger(__name__)


def dispatch_discovery(settings: Settings, scope: str = "pending") -> bool:
    """True if GitHub accepted the request. Never raises: the hourly schedule is the fallback."""
    if not settings.github_token:
        return False
    url = (f"https://api.github.com/repos/{settings.github_repository}/actions/workflows/"
           f"{settings.github_workflow}/dispatches")
    try:
        r = httpx.post(url, timeout=10.0, json={"ref": settings.github_ref, "inputs": {"scope": scope}},
                       headers={"Authorization": f"Bearer {settings.github_token}",
                                "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    except httpx.HTTPError as e:
        log.warning("could not reach GitHub to start discovery: %s", e)
        return False
    if r.status_code == 204:
        return True
    # 401: bad token; 403: token lacks Actions write; 404: wrong repository/workflow or no access.
    log.warning("GitHub refused to start discovery (HTTP %s): %s", r.status_code, r.text[:200])
    return False
