"""Run a mixed workload against both testbed databases for N minutes.

Deliberate problems generated (these are what the rule engine must detect):

  P1  unindexed filter:   SELECT ... FROM orders WHERE customer_id = ?   (seq/full scan)
  P2  N+1 pattern:        1 parent SELECT then per-row order_items lookups
  P3  OFFSET pagination:  ORDER BY id LIMIT 20 OFFSET 100000 on events
  P4  lock contention:    a long transaction holds a row lock while another
                          session waits to update the same row

Plus a background of healthy PK lookups so slow queries stand out.

Usage:
    python testbed/seed/workload.py [--minutes 3] [--engine pg|mysql|both]
"""

from __future__ import annotations

import argparse
import os
import random
import threading
import time

PG_DSN = os.environ.get("PG_DSN", "postgresql://dbdoctor:dbdoctor@127.0.0.1:15432/shop")
MYSQL = {
    "host": os.environ.get("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.environ.get("MYSQL_PORT", "13306")),
    "user": os.environ.get("MYSQL_USER", "dbdoctor"),
    "password": os.environ.get("MYSQL_PASSWORD", "dbdoctor"),
    "database": os.environ.get("MYSQL_DATABASE", "shop"),
}

LOCK_HOLD_SECONDS = 8


def _pg_connect():
    import psycopg

    return psycopg.connect(PG_DSN, autocommit=True)


def _mysql_connect(autocommit: bool = True):
    import pymysql

    return pymysql.connect(**MYSQL, autocommit=autocommit)


def _max_id(cur, table: str) -> int:
    cur.execute(f"SELECT COALESCE(MAX(id), 1) FROM {table}")
    return cur.fetchone()[0]


def _mixed_queries(cur, max_user: int, max_order: int, placeholder: str) -> None:
    """One round of the mixed workload on an open cursor."""
    ph = placeholder

    # healthy background: PK lookups
    for _ in range(10):
        cur.execute(f"SELECT id, email FROM users WHERE id = {ph}", (random.randint(1, max_user),))
        cur.fetchall()

    # P1: unindexed filter on orders.customer_id
    cur.execute(
        f"SELECT id, status, total_cents FROM orders WHERE customer_id = {ph}",
        (random.randint(1, max_user),),
    )
    cur.fetchall()

    # P2: N+1 — one parent query, then a child query per row
    cur.execute(f"SELECT id FROM orders WHERE id > {ph} ORDER BY id LIMIT 20", (max_order // 2,))
    parent_ids = [row[0] for row in cur.fetchall()]
    for oid in parent_ids:
        cur.execute(
            f"SELECT product_id, quantity, price_cents FROM order_items WHERE order_id = {ph}",
            (oid,),
        )
        cur.fetchall()

    # P3: deep OFFSET pagination
    cur.execute(
        f"SELECT id, user_id, kind FROM events ORDER BY id LIMIT 20 OFFSET {ph}",
        (100_000 + random.randint(0, 5) * 20,),
    )
    cur.fetchall()


def _lock_round(connect, begin: str, sleep_stmt: str | None) -> None:
    """P4: hold a row lock in one session while a second session waits on it."""

    def holder():
        conn = connect()
        try:
            cur = conn.cursor()
            cur.execute(begin)
            cur.execute("UPDATE users SET name = 'locked' WHERE id = 1")
            if sleep_stmt:  # sleep server-side so the txn shows as active
                cur.execute(sleep_stmt)
            else:
                time.sleep(LOCK_HOLD_SECONDS)
            cur.execute("ROLLBACK")
        finally:
            conn.close()

    t = threading.Thread(target=holder, daemon=True)
    t.start()
    time.sleep(1)  # let the holder take the lock

    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(begin)
        cur.execute("UPDATE users SET name = 'waiter' WHERE id = 1")  # blocks until rollback
        cur.execute("ROLLBACK")
    finally:
        conn.close()
    t.join()


def run_engine(name: str, minutes: float) -> None:
    if name == "pg":
        connect = _pg_connect
        placeholder, begin = "%s", "BEGIN"
        sleep_stmt = f"SELECT pg_sleep({LOCK_HOLD_SECONDS})"
    else:
        connect = lambda: _mysql_connect()  # noqa: E731
        placeholder, begin = "%s", "START TRANSACTION"
        sleep_stmt = f"SELECT SLEEP({LOCK_HOLD_SECONDS})"

    deadline = time.monotonic() + minutes * 60
    rounds = 0
    conn = connect()
    cur = conn.cursor()
    max_user = _max_id(cur, "users")
    max_order = _max_id(cur, "orders")

    next_lock_round = time.monotonic()  # first lock round immediately
    while time.monotonic() < deadline:
        _mixed_queries(cur, max_user, max_order, placeholder)
        rounds += 1
        if time.monotonic() >= next_lock_round:
            print(f"[{name}] lock-contention round (holds ~{LOCK_HOLD_SECONDS}s)")
            _lock_round(connect, begin, sleep_stmt)
            next_lock_round = time.monotonic() + 60
    conn.close()
    print(f"[{name}] done: {rounds} mixed rounds in {minutes} min")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=float, default=3.0)
    parser.add_argument("--engine", choices=["pg", "mysql", "both"], default="both")
    args = parser.parse_args()

    engines = ["pg", "mysql"] if args.engine == "both" else [args.engine]
    threads = [
        threading.Thread(target=run_engine, args=(e, args.minutes), daemon=True) for e in engines
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
