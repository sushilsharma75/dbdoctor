"""The full audit pipeline must not depend on the platform default encoding.

On Windows the default text encoding is cp1252, which cannot represent
characters the report uses (e.g. the U+2212 minus sign in the score
breakdown). We reproduce that class of failure portably by running the
pipeline under the C locale with UTF-8 mode disabled, which makes Python's
default text encoding ASCII — any file written without an explicit
encoding="utf-8" fails exactly as it does on Windows.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_audit_pipeline_survives_non_utf8_default_encoding(tmp_path):
    env = os.environ | {"LC_ALL": "C", "LANG": "C", "PYTHONUTF8": "0"}
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.audit",
            "--snapshot",
            str(REPO / "fixtures" / "pg_full.json"),
            "--out",
            str(tmp_path),
            "--skip-ai",
            "--skip-pdf",
        ],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "−" in html  # the minus sign that broke cp1252 made it through
