from fastapi import Depends, FastAPI

from furis.api import auth, discovery, public, publications, researchers, users, verification
from furis.api.deps import current_user
from furis.config import get_settings, validate_auth_settings
from furis.models import User
from furis.schemas import Me

# Refuse to start with unsafe or incomplete sign-in configuration.
validate_auth_settings(get_settings())

app = FastAPI(
    title="FURIS API",
    description="Fountain University Research Intelligence System: discover broadly, match carefully, "
    "attribute correctly, report transparently.",
    version="0.1.0",
)
app.include_router(auth.router)
app.include_router(public.router)
app.include_router(users.router)
app.include_router(researchers.router)
app.include_router(discovery.router)
app.include_router(publications.router)
app.include_router(verification.router)
app.include_router(verification.dup_router)


@app.get("/health", tags=["system"])
def health():
    """Liveness plus a database check: 'database' is ok/unreachable, 'schema' is the
    applied migration (null when the tables have not been created yet)."""
    from sqlalchemy import text

    from furis.db import engine

    out = {"status": "ok", "database": "ok", "schema": None}
    try:
        with engine.connect() as conn:
            try:
                out["schema"] = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            except Exception:
                out["schema"] = None  # alembic_version missing: migrations not run
    except Exception:
        out["database"] = "unreachable"
    return out


@app.get("/me", response_model=Me, tags=["system"])
def me(user: User = Depends(current_user)):
    return Me(id=user.id, email=user.email, full_name=user.full_name, role=user.role.value,
              faculty_id=user.faculty_id, researcher_id=user.researcher_id,
              must_change_password=bool(user.must_change_password))
