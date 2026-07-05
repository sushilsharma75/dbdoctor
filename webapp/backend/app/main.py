from fastapi import FastAPI

from webapp.backend.app.config import get_settings

app = FastAPI(title="DBDoctor API")


@app.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "app": settings.app_name, "version": settings.version}
