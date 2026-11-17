from fastapi import Depends, FastAPI

from furis.api.deps import current_user
from furis.models import User
from furis.schemas import Me

from furis.api import discovery, publications, researchers, verification

app = FastAPI(
    title="FURIS API",
    description="Fountain University Research Intelligence System: discover broadly, match carefully, "
    "attribute correctly, report transparently.",
    version="0.1.0",
)
app.include_router(researchers.router)
app.include_router(discovery.router)
app.include_router(publications.router)
app.include_router(verification.router)
app.include_router(verification.dup_router)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


@app.get("/me", response_model=Me, tags=["system"])
def me(user: User = Depends(current_user)):
    return Me(id=user.id, email=user.email, full_name=user.full_name, role=user.role.value,
              faculty_id=user.faculty_id, researcher_id=user.researcher_id)
