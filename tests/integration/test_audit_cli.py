"""T3.5 acceptance: one command produces the complete bundle in < 2 min
on both fixtures (PDF included — needs Chromium, hence integration mark)."""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO = Path(__file__).parent.parent.parent


@pytest.mark.parametrize("fixture", ["pg_full.json", "mysql_full.json"])
def test_full_bundle_under_two_minutes(tmp_path, fixture):
    t0 = time.monotonic()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.audit",
            "--snapshot",
            str(REPO / "fixtures" / fixture),
            "--client-alias",
            "Acme Integration",
            "--out",
            str(tmp_path),
            "--skip-ai",  # offline template text; AI path is unit-tested
        ],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=180,
    )
    elapsed = time.monotonic() - t0
    assert proc.returncode == 0, proc.stderr
    assert elapsed < 120, f"bundle took {elapsed:.0f}s (target < 2 min)"

    html = (tmp_path / "report.html").read_text()
    assert "Acme Integration" in html

    pdf = (tmp_path / "report.pdf").read_bytes()
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 20_000  # a real multi-page document, not an empty shell

    tasks = (tmp_path / "tasks.md").read_text()
    assert "# [DB]" in tasks and "Staging test plan" in tasks

    findings = json.loads((tmp_path / "findings.json").read_text())
    assert findings["score"]["score"] > 0
    assert findings["findings"], "findings.json must carry the findings"

    # stage timings are logged
    for stage in ("validate snapshot", "run rules + score", "render HTML", "render PDF"):
        assert stage in proc.stdout, stage
