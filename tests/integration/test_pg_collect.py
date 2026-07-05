"""Integration: run the PG collector against the docker-compose testbed.

Requires `make testbed-up && make testbed-seed && make testbed-load` first.
Run with: pytest -m integration
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
PG_DSN = os.environ.get("PG_DSN", "postgresql://dbdoctor:dbdoctor@127.0.0.1:15432/shop")
# 'postgres' db exists in the same container but has no pg_stat_statements extension
PG_DSN_NO_EXT = os.environ.get(
    "PG_DSN_NO_EXT", "postgresql://dbdoctor:dbdoctor@127.0.0.1:15432/postgres"
)


def run_collector(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO / "collector" / "pg_collect.py"), *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_collector_output_validates_against_snapshot_schema(tmp_path):
    out = tmp_path / "snapshot.json"
    proc = run_collector("--dsn", PG_DSN, "--out", str(out))
    assert proc.returncode == 0, proc.stderr
    assert "sha256=" in proc.stdout  # supply-chain check: script names its own hash

    snap = Snapshot.model_validate(json.loads(out.read_text()))

    assert snap.meta.engine == "postgres"
    assert "query_stats" in snap.meta.capabilities
    assert snap.connections is not None and snap.connections.max_limit > 0
    assert len(snap.settings) >= 20
    assert snap.meta.db_size_bytes and snap.meta.db_size_bytes > 0

    # the testbed's planted problems must be visible in the raw snapshot
    table_names = {t.name for t in snap.tables}
    assert {"users", "orders", "order_items", "events"} <= table_names
    orders = next(t for t in snap.tables if t.name == "orders")
    assert orders.seq_scans and orders.seq_scans > 0  # P1 unindexed filter scans

    index_names = {i.name for i in snap.indexes}
    assert {"users_email_idx", "users_email_dup_idx"} <= index_names  # P5 duplicate pair

    if snap.queries:  # workload ran: P1 query captured with literals stripped
        all_sql = " ".join(q.normalized_sql for q in snap.queries)
        assert "customer_id = ?" in all_sql
        assert "@example.com" not in all_sql


def test_no_literals_or_names_leak(tmp_path):
    out = tmp_path / "snapshot.json"
    proc = run_collector("--dsn", PG_DSN, "--out", str(out))
    assert proc.returncode == 0, proc.stderr
    raw = out.read_text()
    assert "dbdoctor:dbdoctor@" not in raw  # credentials never in output
    snap = json.loads(raw)
    assert "shop" not in snap["meta"]["host_alias"]  # dbname hashed by default


def test_missing_extension_degrades_gracefully(tmp_path):
    """T2.4: a database without pg_stat_statements yields exit 0 + guide."""
    out = tmp_path / "degraded.json"
    proc = run_collector("--dsn", PG_DSN_NO_EXT, "--out", str(out))
    assert proc.returncode == 0, proc.stderr
    assert "pg_stat_statements is not enabled" in proc.stdout
    assert "RDS" in proc.stdout and "Cloud SQL" in proc.stdout

    snap = Snapshot.model_validate(json.loads(out.read_text()))
    assert "query_stats" not in snap.meta.capabilities
    assert snap.queries == []
    assert snap.meta.capability_notes


def test_delta_mode_end_to_end(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    assert run_collector("--dsn", PG_DSN, "--out", str(first)).returncode == 0

    # nudge counters between snapshots
    import psycopg

    with psycopg.connect(PG_DSN, autocommit=True) as conn, conn.cursor() as cur:
        for _ in range(5):
            cur.execute("SELECT count(*) FROM orders WHERE customer_id = 7")

    # backdate the first snapshot so the interval is meaningful
    data = json.loads(first.read_text())
    data["meta"]["collected_at"] = "2026-07-04T00:00:00+00:00"
    first.write_text(json.dumps(data))

    proc = run_collector("--dsn", PG_DSN, "--out", str(second), "--delta-of", str(first))
    assert proc.returncode == 0, proc.stderr

    snap = Snapshot.model_validate(json.loads(second.read_text()))
    assert snap.meta.is_delta is True
    assert snap.meta.delta_interval_seconds and snap.meta.delta_interval_seconds > 0
    rated = [q for q in snap.queries if q.calls_per_day is not None]
    assert rated, "delta mode must produce per-day rates"
