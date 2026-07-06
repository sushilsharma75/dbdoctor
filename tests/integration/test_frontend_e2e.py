"""T4.2 acceptance: the full signup → wizard → upload → dashboard flow works
against a real backend + built frontend, driven by a real browser.

Requires `npm install && npm run build` in webapp/frontend (CI does this).
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from report.pdf import _find_system_chromium

pytestmark = pytest.mark.integration

REPO = Path(__file__).parent.parent.parent
FRONTEND = REPO / "webapp" / "frontend"
API_PORT = 8000  # NEXT_PUBLIC_API_URL default is baked at build time
WEB_PORT = 3000


def _wait_http(url: str, timeout_s: int = 60) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:
            time.sleep(0.5)
    raise TimeoutError(f"{url} did not come up in {timeout_s}s")


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    if not (FRONTEND / ".next").exists():
        pytest.skip("frontend not built (run: cd webapp/frontend && npm run build)")
    data = tmp_path_factory.mktemp("e2e")
    env = os.environ | {
        "DBDOCTOR_DATABASE_URL": f"sqlite:///{data}/e2e.db",
        "DBDOCTOR_DATA_DIR": str(data / "files"),
        "DBDOCTOR_JWT_SECRET": "e2e-secret-of-at-least-thirty-two-bytes",
        "DBDOCTOR_ADMIN_EMAILS": "founder@dbdoctor-admin.io",
        "DBDOCTOR_ENABLE_PDF": "false",
    }
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "webapp.backend.app.main:app", "--port", str(API_PORT)],
        cwd=REPO,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    web = subprocess.Popen(
        ["npm", "run", "start", "--", "-p", str(WEB_PORT)],
        cwd=FRONTEND,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_http(f"http://127.0.0.1:{API_PORT}/health")
        _wait_http(f"http://127.0.0.1:{WEB_PORT}/")
        yield f"http://127.0.0.1:{WEB_PORT}"
    finally:
        api.terminate()
        web.terminate()
        api.wait(timeout=10)
        web.wait(timeout=10)


def test_signup_upload_review_approve_flow(stack):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:
            browser = p.chromium.launch(executable_path=_find_system_chromium())
        page = browser.new_page()

        # landing page carries the security-model positioning
        page.goto(stack)
        expect(page.get_by_text("without handing anyone your credentials")).to_be_visible()

        # sign up
        page.goto(f"{stack}/login")
        page.get_by_test_id("toggle-mode").click()
        page.get_by_test_id("email").fill("dev@dbdoctor.io")
        page.get_by_test_id("password").fill("hunter2hunter2")
        page.get_by_test_id("submit").click()
        page.wait_for_url("**/dashboard")
        expect(page.get_by_test_id("empty")).to_be_visible()

        # wizard: engine -> collector instructions -> upload snapshot
        page.goto(f"{stack}/new-audit")
        page.get_by_test_id("engine-postgres").click()
        expect(page.get_by_test_id("step-collector")).to_contain_text("pg_collect.py")
        expect(page.get_by_test_id("step-collector")).to_contain_text("read-only")
        page.get_by_test_id("collector-done").click()
        page.get_by_test_id("alias").fill("Acme Production")
        page.get_by_test_id("snapshot-file").set_input_files(REPO / "fixtures" / "pg_full.json")
        page.get_by_test_id("upload").click()

        # dashboard: job appears, held in expert review
        page.wait_for_url("**/dashboard")
        expect(page.get_by_test_id("job-row")).to_contain_text("Acme Production")
        expect(page.get_by_test_id("job-status")).to_have_text(
            "expert review in progress", timeout=15_000
        )

        # founder approves via the admin dashboard
        admin = browser.new_page()
        admin.goto(f"{stack}/login")
        admin.get_by_test_id("toggle-mode").click()
        admin.get_by_test_id("email").fill("founder@dbdoctor-admin.io")
        admin.get_by_test_id("password").fill("hunter2hunter2")
        admin.get_by_test_id("submit").click()
        admin.wait_for_url("**/dashboard")
        admin.get_by_test_id("approve").click()
        expect(admin.get_by_test_id("job-status")).to_have_text("ready", timeout=10_000)

        # the customer's dashboard reflects it after the next poll
        expect(page.get_by_test_id("job-status")).to_have_text("ready", timeout=15_000)

        browser.close()


def test_bad_upload_shows_helpful_error(stack, tmp_path):
    from playwright.sync_api import expect, sync_playwright

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"not": "a snapshot"}))

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:
            browser = p.chromium.launch(executable_path=_find_system_chromium())
        page = browser.new_page()
        page.goto(f"{stack}/login")
        page.get_by_test_id("email").fill("dev@dbdoctor.io")
        page.get_by_test_id("password").fill("hunter2hunter2")
        page.get_by_test_id("submit").click()
        page.wait_for_url("**/dashboard")

        page.goto(f"{stack}/new-audit")
        page.get_by_test_id("engine-mysql").click()
        page.get_by_test_id("collector-done").click()
        page.get_by_test_id("snapshot-file").set_input_files(bad)
        page.get_by_test_id("upload").click()
        expect(page.get_by_test_id("upload-error")).to_contain_text("not a valid dbdoctor snapshot")
        browser.close()
