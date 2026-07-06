from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from webapp.backend.app import auth, billing, jobs
from webapp.backend.app.config import get_settings

app = FastAPI(title="DBDoctor API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(billing.router)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COLLECTORS = {"postgres": "pg_collect.py", "mysql": "mysql_collect.py"}


@app.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "app": settings.app_name, "version": settings.version}


@app.get("/collectors/{engine}")
def download_collector(engine: str) -> FileResponse:
    """Public download of the single-file collector (dist build preferred)."""
    name = _COLLECTORS.get(engine)
    if name is None:
        raise HTTPException(404, "unknown engine (use 'postgres' or 'mysql')")
    for base in (_REPO_ROOT / "dist", _REPO_ROOT / "collector"):
        if (base / name).exists():
            return FileResponse(base / name, filename=name, media_type="text/x-python")
    raise HTTPException(404, "collector artifact not built (run make dist)")
