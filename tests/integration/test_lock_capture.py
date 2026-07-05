"""T2.8/T2.12 acceptance: a live lock wait is captured by both collectors
and, once it exceeds the threshold, fires R-L1 in the rule engine."""

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from engine.models import Snapshot
from tests.integration.test_mysql_collect import MYSQL_DSN
from tests.integration.test_pg_collect import PG_DSN

pytestmark = pytest.mark.integration

REPO = Path(__file__).parent.parent.parent
HOLD_SECONDS = 12


def _capture_during_block(engine: str, holder_connect, waiter_connect, tmp_path) -> Snapshot:
    """Hold a row lock, let a second session block on it, run the collector."""
    release = threading.Event()

    def holder():
        conn = holder_connect()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE users SET name = 'locked' WHERE id = 1")
            release.wait(HOLD_SECONDS)
            conn.rollback()
        finally:
            conn.close()

    def waiter():
        conn = waiter_connect()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE users SET name = 'waiter' WHERE id = 1")  # blocks
            conn.rollback()
        finally:
            conn.close()

    t_hold = threading.Thread(target=holder, daemon=True)
    t_hold.start()
    time.sleep(1)
    t_wait = threading.Thread(target=waiter, daemon=True)
    t_wait.start()
    time.sleep(6.5)  # long enough that the wait crosses the R-L1 threshold (5s)

    out = tmp_path / "lock_snapshot.json"
    script = "pg_collect.py" if engine == "pg" else "mysql_collect.py"
    dsn = PG_DSN if engine == "pg" else MYSQL_DSN
    proc = subprocess.run(
        [sys.executable, str(REPO / "collector" / script), "--dsn", dsn, "--out", str(out)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    release.set()
    t_hold.join(timeout=HOLD_SECONDS)
    t_wait.join(timeout=HOLD_SECONDS)
    assert proc.returncode == 0, proc.stderr
    return Snapshot.model_validate(json.loads(out.read_text()))


def test_pg_lock_wait_captured(tmp_path):
    import psycopg

    snap = _capture_during_block(
        "pg",
        lambda: psycopg.connect(PG_DSN),
        lambda: psycopg.connect(PG_DSN),
        tmp_path,
    )
    assert snap.lock_waits, "blocked session not captured in lock_waits"
    lw = snap.lock_waits[0]
    assert lw.blocked_digest and lw.blocker_digest

    # T2.12: the captured lock chain fires R-L1
    from engine.run import run_all

    l1 = [f for f in run_all(snap).findings if f.rule_id == "R-L1"]
    assert l1, f"R-L1 did not fire (wait_ms={lw.wait_ms})"
    assert l1[0].evidence["blocker_digest"] == lw.blocker_digest


def test_mysql_lock_wait_captured(tmp_path):
    import pymysql

    from collector.mysql_collect import parse_dsn

    params = parse_dsn(MYSQL_DSN)

    def connect():
        conn = pymysql.connect(**params, autocommit=False)
        conn.begin()
        return conn

    snap = _capture_during_block("mysql", connect, connect, tmp_path)
    assert snap.lock_waits, "blocked session not captured in lock_waits"

    from engine.run import run_all

    l1 = [f for f in run_all(snap).findings if f.rule_id == "R-L1"]
    assert l1, f"R-L1 did not fire (wait_ms={snap.lock_waits[0].wait_ms})"
