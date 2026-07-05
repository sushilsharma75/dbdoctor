"""Integration: run the MySQL collector against the testbed MySQL 8 and
MariaDB 11 containers.

Requires `make testbed-up && make testbed-seed && make testbed-load` first
(MariaDB is seeded separately: MYSQL_PORT=13307 python testbed/seed/seed.py
--engine mysql). Run with: pytest -m integration
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from engine.models import Snapshot

pytestmark = pytest.mark.integration

REPO = Path(__file__).parent.parent.parent
MYSQL_DSN = os.environ.get("MYSQL_DSN", "mysql://dbdoctor:dbdoctor@127.0.0.1:13306/shop")
MARIADB_DSN = os.environ.get("MARIADB_DSN", "mysql://dbdoctor:dbdoctor@127.0.0.1:13307/shop")


def run_collector(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO / "collector" / "mysql_collect.py"), *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_mysql8_output_validates_and_shows_planted_problems(tmp_path):
    out = tmp_path / "snapshot.json"
    proc = run_collector("--dsn", MYSQL_DSN, "--out", str(out))
    assert proc.returncode == 0, proc.stderr
    assert "sha256=" in proc.stdout

    snap = Snapshot.model_validate(json.loads(out.read_text()))

    assert snap.meta.engine == "mysql"
    assert "query_stats" in snap.meta.capabilities
    assert "sys_schema" in snap.meta.capabilities
    assert snap.connections and snap.connections.max_limit > 0
    assert snap.connections.peak is not None  # Max_used_connections
    assert len(snap.settings) >= 25

    table_names = {t.name for t in snap.tables}
    assert {"users", "orders", "order_items", "events"} <= table_names

    # P1: the unindexed customer_id filter must be a full-scan digest with
    # rows_examined >> rows_returned
    p1 = [q for q in snap.queries if "customer_id" in q.normalized_sql and q.full_scan_flag]
    assert p1, "planted full-scan query not captured"
    assert p1[0].rows_examined and p1[0].rows_examined > p1[0].rows_returned * 100

    # P5: duplicate index pair flagged via sys.schema_redundant_indexes
    dup = [i for i in snap.indexes if i.is_duplicate_candidate]
    assert any("users" in i.table for i in dup), "planted duplicate index not flagged"

    # digests are normalized; nothing literal-looking survives
    all_sql = " ".join(q.normalized_sql for q in snap.queries)
    assert "@example.com" not in all_sql


def test_mysql8_quantiles_and_no_leaks(tmp_path):
    out = tmp_path / "snapshot.json"
    proc = run_collector("--dsn", MYSQL_DSN, "--out", str(out))
    assert proc.returncode == 0, proc.stderr

    raw = out.read_text()
    assert "dbdoctor:dbdoctor@" not in raw

    snap = Snapshot.model_validate(json.loads(raw))
    assert "shop" not in snap.meta.host_alias  # hashed by default
    assert any(q.p95_time_ms is not None for q in snap.queries)  # MySQL 8 quantiles


def test_mariadb_degrades_gracefully(tmp_path):
    """T2.7 acceptance: MariaDB run exits 0 with capability flags."""
    out = tmp_path / "mariadb.json"
    proc = run_collector("--dsn", MARIADB_DSN, "--out", str(out))
    assert proc.returncode == 0, proc.stderr

    snap = Snapshot.model_validate(json.loads(out.read_text()))
    assert snap.meta.engine == "mariadb"
    assert "sys_schema" not in snap.meta.capabilities
    assert any("MariaDB" in n for n in snap.meta.capability_notes)

    # tables + indexes still collected through information_schema fallbacks
    assert {t.name for t in snap.tables} >= {"users", "orders"}
    assert any(i.name == "users_email_dup_idx" for i in snap.indexes)

    # MariaDB ships performance_schema OFF by default; whichever way the
    # testbed configures it, the snapshot must degrade coherently
    if "query_stats" not in snap.meta.capabilities:
        assert snap.queries == []
        assert "statements_digest" in proc.stdout or "performance_schema" in proc.stdout
    else:
        assert all(q.p95_time_ms is None for q in snap.queries)  # no quantiles on MariaDB
