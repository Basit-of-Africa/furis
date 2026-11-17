from fastapi import FastAPI

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
