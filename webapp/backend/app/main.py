from fastapi import FastAPI

from webapp.backend.app import auth, billing, jobs
from webapp.backend.app.config import get_settings

app = FastAPI(title="DBDoctor API")
app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(billing.router)


@app.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "app": settings.app_name, "version": settings.version}
