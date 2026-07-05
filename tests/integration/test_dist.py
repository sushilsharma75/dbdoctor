"""T2.8 acceptance: dist artifacts run standalone (no repo, no delta.py)."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from engine.models import Snapshot
from tests.integration.test_mysql_collect import MYSQL_DSN
from tests.integration.test_pg_collect import PG_DSN

pytestmark = pytest.mark.integration

REPO = Path(__file__).parent.parent.parent


@pytest.fixture(scope="module")
def dist_dir(tmp_path_factory) -> Path:
    subprocess.run(
        [sys.executable, str(REPO / "tools" / "build_dist.py")], check=True, capture_output=True
    )
    # copy the artifacts away from the repo so nothing can be imported from it
    isolated = tmp_path_factory.mktemp("dist_isolated")
    for name in ("pg_collect.py", "mysql_collect.py"):
        shutil.copy(REPO / "dist" / name, isolated / name)
    return isolated


@pytest.mark.parametrize(
    ("script", "dsn"),
    [("pg_collect.py", PG_DSN), ("mysql_collect.py", MYSQL_DSN)],
    ids=["pg", "mysql"],
)
def test_dist_artifact_standalone_with_delta(dist_dir, tmp_path, script, dsn):
    first = tmp_path / "first.json"
    proc = subprocess.run(
        [sys.executable, str(dist_dir / script), "--dsn", dsn, "--out", str(first)],
        capture_output=True,
        text=True,
        cwd=dist_dir,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "sha256=" in proc.stdout

    # delta mode must work WITHOUT delta.py on disk (it is inlined)
    data = json.loads(first.read_text())
    data["meta"]["collected_at"] = "2026-07-04T00:00:00+00:00"
    first.write_text(json.dumps(data))

    second = tmp_path / "second.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(dist_dir / script),
            "--dsn",
            dsn,
            "--out",
            str(second),
            "--delta-of",
            str(first),
        ],
        capture_output=True,
        text=True,
        cwd=dist_dir,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr

    snap = Snapshot.model_validate(json.loads(second.read_text()))
    assert snap.meta.is_delta is True


def test_checksum_files_written(dist_dir):
    for name in ("pg_collect.py", "mysql_collect.py"):
        sha_file = REPO / "dist" / f"{name}.sha256"
        assert sha_file.exists()
        digest, _, filename = sha_file.read_text().strip().partition("  ")
        assert len(digest) == 64 and filename == name
