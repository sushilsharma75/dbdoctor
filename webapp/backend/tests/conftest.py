import pytest
from fastapi.testclient import TestClient

from webapp.backend.app.config import get_settings
from webapp.backend.app.db import reset_engine_for_tests


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A TestClient on a fresh sqlite DB + data dir per test."""
    monkeypatch.setenv("DBDOCTOR_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("DBDOCTOR_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DBDOCTOR_JWT_SECRET", "test-secret-of-at-least-thirty-two-bytes!")
    monkeypatch.setenv("DBDOCTOR_ADMIN_EMAILS", "founder@dbdoctor-admin.io")
    monkeypatch.setenv("DBDOCTOR_ENABLE_PDF", "false")  # pipeline speed in unit tests
    monkeypatch.setenv("DBDOCTOR_ENABLE_AI", "false")
    get_settings.cache_clear()
    reset_engine_for_tests()

    from webapp.backend.app.main import app

    with TestClient(app) as tc:
        yield tc

    get_settings.cache_clear()
    reset_engine_for_tests()


def register(client: TestClient, email: str, password: str = "hunter2hunter2") -> dict:
    resp = client.post("/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}
