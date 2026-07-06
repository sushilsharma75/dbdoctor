"""T4.1 acceptance: invalid snapshot rejected with a helpful error;
report inaccessible until approved; authz enforced."""

import io
import json
from pathlib import Path

from webapp.backend.tests.conftest import register

FIXTURE = Path(__file__).parent.parent.parent.parent / "fixtures" / "pg_full.json"


def _upload(client, headers, content: bytes, alias="acme"):
    return client.post(
        "/jobs",
        headers=headers,
        files={"snapshot": ("snapshot.json", io.BytesIO(content), "application/json")},
        data={"client_alias": alias},
    )


def test_invalid_snapshot_rejected_with_helpful_error(client):
    headers = register(client, "dev@dbdoctor.io")

    resp = _upload(client, headers, b"this is not json")
    assert resp.status_code == 422
    assert "not valid JSON" in resp.json()["detail"]

    resp = _upload(client, headers, json.dumps({"meta": {"engine": "postgres"}}).encode())
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "not a valid dbdoctor snapshot" in detail
    assert "pg_collect.py" in detail  # tells the user how to fix it


def test_upload_runs_pipeline_into_review_hold(client):
    headers = register(client, "dev@dbdoctor.io")
    resp = _upload(client, headers, FIXTURE.read_bytes())
    assert resp.status_code == 201
    job_id = resp.json()["id"]
    assert resp.json()["engine"] == "postgres"

    # TestClient runs background tasks before returning; job is now in review
    job = client.get(f"/jobs/{job_id}", headers=headers).json()
    assert job["status"] == "review"
    assert job["score"] is not None

    # review hold: the customer cannot fetch the report yet
    resp = client.get(f"/jobs/{job_id}/report?fmt=html", headers=headers)
    assert resp.status_code == 409
    assert "not available yet" in resp.json()["detail"]


def test_admin_approval_releases_report(client):
    dev = register(client, "dev@dbdoctor.io")
    admin = register(client, "founder@dbdoctor-admin.io")

    job_id = _upload(client, dev, FIXTURE.read_bytes()).json()["id"]

    # only admins may approve
    assert client.post(f"/jobs/{job_id}/approve", headers=dev).status_code == 403

    # admin can inspect the held report before approving (founder review)
    resp = client.get(f"/jobs/{job_id}/report?fmt=html", headers=admin)
    assert resp.status_code == 200

    assert client.post(f"/jobs/{job_id}/approve", headers=admin).status_code == 200

    resp = client.get(f"/jobs/{job_id}/report?fmt=html", headers=dev)
    assert resp.status_code == 200
    assert "Database Performance Audit" in resp.text

    tasks = client.get(f"/jobs/{job_id}/report?fmt=tasks", headers=dev)
    assert "# [DB]" in tasks.text


def test_double_approval_rejected(client):
    dev = register(client, "dev@dbdoctor.io")
    admin = register(client, "founder@dbdoctor-admin.io")
    job_id = _upload(client, dev, FIXTURE.read_bytes()).json()["id"]
    assert client.post(f"/jobs/{job_id}/approve", headers=admin).status_code == 200
    assert client.post(f"/jobs/{job_id}/approve", headers=admin).status_code == 409


def test_users_cannot_see_each_others_jobs(client):
    alice = register(client, "alice@dbdoctor.io")
    bob = register(client, "bob@dbdoctor.io")

    job_id = _upload(client, alice, FIXTURE.read_bytes()).json()["id"]

    # bob can neither read nor fetch alice's job — and can't tell it exists
    assert client.get(f"/jobs/{job_id}", headers=bob).status_code == 404
    assert client.get(f"/jobs/{job_id}/report", headers=bob).status_code == 404
    assert client.get("/jobs", headers=bob).json() == []
    assert len(client.get("/jobs", headers=alice).json()) == 1


def test_oversized_upload_rejected(client, monkeypatch):
    from webapp.backend.app.config import get_settings

    monkeypatch.setenv("DBDOCTOR_MAX_UPLOAD_BYTES", "100")
    get_settings.cache_clear()
    headers = register(client, "dev@dbdoctor.io")
    resp = _upload(client, headers, FIXTURE.read_bytes())
    assert resp.status_code == 413
