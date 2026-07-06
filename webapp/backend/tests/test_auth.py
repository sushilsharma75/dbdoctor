from webapp.backend.tests.conftest import register


def test_register_login_roundtrip(client):
    register(client, "dev@dbdoctor.io")
    resp = client.post(
        "/auth/login", json={"email": "dev@dbdoctor.io", "password": "hunter2hunter2"}
    )
    assert resp.status_code == 200
    assert resp.json()["is_admin"] is False


def test_admin_flag_from_settings(client):
    resp = client.post(
        "/auth/register",
        json={"email": "founder@dbdoctor-admin.io", "password": "hunter2hunter2"},
    )
    assert resp.json()["is_admin"] is True


def test_duplicate_email_rejected(client):
    register(client, "dup@dbdoctor.io")
    resp = client.post(
        "/auth/register", json={"email": "dup@dbdoctor.io", "password": "hunter2hunter2"}
    )
    assert resp.status_code == 409


def test_wrong_password_rejected(client):
    register(client, "dev@dbdoctor.io")
    resp = client.post("/auth/login", json={"email": "dev@dbdoctor.io", "password": "wrongwrong"})
    assert resp.status_code == 401


def test_requests_require_token(client):
    assert client.get("/jobs").status_code == 401
    bad = {"Authorization": "Bearer not-a-token"}
    assert client.get("/jobs", headers=bad).status_code == 401
