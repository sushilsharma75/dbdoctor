from webapp.backend.tests.conftest import register


def test_register_login_roundtrip(client):
    register(client, "dev@dbdoctor.io")
    resp = client.post(
        "/auth/login", json={"email": "dev@dbdoctor.io", "password": "hunter2hunter2"}
    )
    assert resp.status_code == 200
    assert resp.json()["is_admin"] is False


def test_signup_cannot_claim_admin_from_settings(client):
    resp = client.post(
        "/auth/register",
        json={"email": "founder@dbdoctor-admin.io", "password": "hunter2hunter2"},
    )
    assert resp.json()["is_admin"] is False
    response = client.post(
        "/auth/login", json={"email": "founder@dbdoctor-admin.io", "password": "hunter2hunter2"}
    )
    assert response.json()["is_admin"] is False


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


def test_trusted_provisioning_and_revocation(client):
    from click.testing import CliRunner

    from cli.admin import main
    from webapp.backend.tests.conftest import provision_admin

    admin = provision_admin(client)
    result = CliRunner().invoke(main, ["--email", "founder@dbdoctor-admin.io", "--revoke"])
    assert result.exit_code == 0
    assert client.post("/jobs/unknown/approve", headers=admin).status_code == 403


def test_provisioning_cannot_silently_promote_existing_signup(client):
    from click.testing import CliRunner

    from cli.admin import main

    register(client, "existing@dbdoctor.io")
    result = CliRunner().invoke(main, ["--email", "existing@dbdoctor.io"])
    assert result.exit_code != 0
    assert "Verify" in result.output


def test_long_utf8_password_is_validation_error(client):
    response = client.post("/auth/register", json={"email": "x@dbdoctor.io", "password": "😀" * 20})
    assert response.status_code == 422


def test_production_refuses_default_signing_key():
    import pytest
    from pydantic import ValidationError

    from webapp.backend.app.config import Settings

    with pytest.raises(ValidationError, match="random JWT secret"):
        Settings(env="production", jwt_secret="dev-secret-change-me", _env_file=None)
