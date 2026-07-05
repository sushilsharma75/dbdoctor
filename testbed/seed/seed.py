"""Seed the testbed databases with an ecommerce-like schema and bulk rows.

Creates users / orders / order_items / events in both PostgreSQL and MySQL,
with deliberate problems the rule engine must later detect:

  * NO index on orders.customer_id            (missing-index candidate)
  * duplicate index on users(email)           (duplicate-index finding)

Row generation happens server-side (generate_series / INSERT-SELECT doubling)
so seeding millions of rows takes minutes, not hours.

Usage:
    python testbed/seed/seed.py [--scale 1.0] [--engine pg|mysql|both]

At --scale 1.0 (default): users 1M, orders 2M, order_items 4M, events 2M.
Use --scale 0.01 for a quick smoke run.
"""

from __future__ import annotations

import argparse
import os
import time

BASE_ROWS = {
    "users": 1_000_000,
    "orders": 2_000_000,
    "order_items": 4_000_000,
    "events": 2_000_000,
}

PG_DSN = os.environ.get("PG_DSN", "postgresql://dbdoctor:dbdoctor@127.0.0.1:15432/shop")
MYSQL = {
    "host": os.environ.get("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.environ.get("MYSQL_PORT", "13306")),
    "user": os.environ.get("MYSQL_USER", "dbdoctor"),
    "password": os.environ.get("MYSQL_PASSWORD", "dbdoctor"),
    "database": os.environ.get("MYSQL_DATABASE", "shop"),
}


def counts(scale: float) -> dict[str, int]:
    return {t: max(1000, int(n * scale)) for t, n in BASE_ROWS.items()}


# --------------------------------------------------------------------------- PG

PG_SCHEMA = """
DROP TABLE IF EXISTS order_items, orders, events, users CASCADE;

CREATE TABLE users (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email       text NOT NULL,
    name        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX users_email_idx ON users (email);
-- DELIBERATE PROBLEM: duplicate index on users(email)
CREATE INDEX users_email_dup_idx ON users (email);

CREATE TABLE orders (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id  bigint NOT NULL,   -- DELIBERATE PROBLEM: no index
    status       text NOT NULL,
    total_cents  bigint NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE order_items (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id     bigint NOT NULL,
    product_id   bigint NOT NULL,
    quantity     int NOT NULL,
    price_cents  bigint NOT NULL
);
CREATE INDEX order_items_order_id_idx ON order_items (order_id);

CREATE TABLE events (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     bigint NOT NULL,
    kind        text NOT NULL,
    payload     text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
"""


def seed_pg(n: dict[str, int]) -> None:
    import psycopg

    print(f"[pg] connecting to {PG_DSN}")
    with psycopg.connect(PG_DSN, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(PG_SCHEMA)
        t0 = time.monotonic()
        cur.execute(
            """
            INSERT INTO users (email, name, created_at)
            SELECT 'user' || g || '@example.com',
                   'User ' || g,
                   now() - (random() * interval '365 days')
            FROM generate_series(1, %s) g
            """,
            (n["users"],),
        )
        cur.execute(
            """
            INSERT INTO orders (customer_id, status, total_cents, created_at)
            SELECT 1 + floor(random() * %s)::bigint,
                   (ARRAY['pending','paid','shipped','cancelled'])[1 + floor(random()*4)::int],
                   (random() * 50000)::bigint,
                   now() - (random() * interval '180 days')
            FROM generate_series(1, %s) g
            """,
            (n["users"], n["orders"]),
        )
        cur.execute(
            """
            INSERT INTO order_items (order_id, product_id, quantity, price_cents)
            SELECT 1 + floor(random() * %s)::bigint,
                   1 + floor(random() * 5000)::bigint,
                   1 + floor(random() * 5)::int,
                   (random() * 20000)::bigint
            FROM generate_series(1, %s) g
            """,
            (n["orders"], n["order_items"]),
        )
        cur.execute(
            """
            INSERT INTO events (user_id, kind, payload, created_at)
            SELECT 1 + floor(random() * %s)::bigint,
                   (ARRAY['login','view','cart','checkout'])[1 + floor(random()*4)::int],
                   md5(g::text),
                   now() - (random() * interval '90 days')
            FROM generate_series(1, %s) g
            """,
            (n["users"], n["events"]),
        )
        cur.execute("ANALYZE")
        print(f"[pg] seeded {sum(n.values()):,} rows in {time.monotonic() - t0:.1f}s")


# ------------------------------------------------------------------------ MySQL

MYSQL_SCHEMA = [
    "DROP TABLE IF EXISTS order_items",
    "DROP TABLE IF EXISTS orders",
    "DROP TABLE IF EXISTS events",
    "DROP TABLE IF EXISTS users",
    """
    CREATE TABLE users (
        id          bigint NOT NULL AUTO_INCREMENT PRIMARY KEY,
        email       varchar(255) NOT NULL,
        name        varchar(255) NOT NULL,
        created_at  datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY users_email_idx (email),
        KEY users_email_dup_idx (email)  -- DELIBERATE PROBLEM: duplicate index
    ) ENGINE=InnoDB
    """,
    """
    CREATE TABLE orders (
        id           bigint NOT NULL AUTO_INCREMENT PRIMARY KEY,
        customer_id  bigint NOT NULL,   -- DELIBERATE PROBLEM: no index
        status       varchar(16) NOT NULL,
        total_cents  bigint NOT NULL,
        created_at   datetime NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB
    """,
    """
    CREATE TABLE order_items (
        id           bigint NOT NULL AUTO_INCREMENT PRIMARY KEY,
        order_id     bigint NOT NULL,
        product_id   bigint NOT NULL,
        quantity     int NOT NULL,
        price_cents  bigint NOT NULL,
        KEY order_items_order_id_idx (order_id)
    ) ENGINE=InnoDB
    """,
    """
    CREATE TABLE events (
        id          bigint NOT NULL AUTO_INCREMENT PRIMARY KEY,
        user_id     bigint NOT NULL,
        kind        varchar(16) NOT NULL,
        payload     varchar(64),
        created_at  datetime NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB
    """,
]


def _mysql_double_to(cur, table: str, insert_double_sql: str, seed_sql: str, target: int) -> None:
    """Grow a table to ~target rows by repeated INSERT ... SELECT doubling."""
    cur.execute(seed_sql)
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    current = cur.fetchone()[0]
    while current < target:
        remaining = target - current
        cur.execute(insert_double_sql + f" LIMIT {min(current, remaining)}")
        current += min(current, remaining)


def seed_mysql(n: dict[str, int]) -> None:
    import pymysql

    print(f"[mysql] connecting to {MYSQL['host']}:{MYSQL['port']}")
    conn = pymysql.connect(**MYSQL, autocommit=True)
    t0 = time.monotonic()
    with conn.cursor() as cur:
        for stmt in MYSQL_SCHEMA:
            cur.execute(stmt)

        _mysql_double_to(
            cur,
            "users",
            """
            INSERT INTO users (email, name, created_at)
            SELECT CONCAT('user', FLOOR(RAND() * 1000000000), '@example.com'),
                   CONCAT('User ', id),
                   NOW() - INTERVAL FLOOR(RAND() * 365) DAY
            FROM users
            """,
            "INSERT INTO users (email, name) VALUES ('user1@example.com', 'User 1')",
            n["users"],
        )
        _mysql_double_to(
            cur,
            "orders",
            f"""
            INSERT INTO orders (customer_id, status, total_cents, created_at)
            SELECT 1 + FLOOR(RAND() * {n["users"]}),
                   ELT(1 + FLOOR(RAND() * 4), 'pending', 'paid', 'shipped', 'cancelled'),
                   FLOOR(RAND() * 50000),
                   NOW() - INTERVAL FLOOR(RAND() * 180) DAY
            FROM orders
            """,
            "INSERT INTO orders (customer_id, status, total_cents) VALUES (1, 'pending', 100)",
            n["orders"],
        )
        _mysql_double_to(
            cur,
            "order_items",
            f"""
            INSERT INTO order_items (order_id, product_id, quantity, price_cents)
            SELECT 1 + FLOOR(RAND() * {n["orders"]}),
                   1 + FLOOR(RAND() * 5000),
                   1 + FLOOR(RAND() * 5),
                   FLOOR(RAND() * 20000)
            FROM order_items
            """,
            "INSERT INTO order_items (order_id, product_id, quantity, price_cents)"
            " VALUES (1, 1, 1, 100)",
            n["order_items"],
        )
        _mysql_double_to(
            cur,
            "events",
            f"""
            INSERT INTO events (user_id, kind, payload, created_at)
            SELECT 1 + FLOOR(RAND() * {n["users"]}),
                   ELT(1 + FLOOR(RAND() * 4), 'login', 'view', 'cart', 'checkout'),
                   MD5(RAND()),
                   NOW() - INTERVAL FLOOR(RAND() * 90) DAY
            FROM events
            """,
            "INSERT INTO events (user_id, kind, payload) VALUES (1, 'login', 'x')",
            n["events"],
        )
        cur.execute("ANALYZE TABLE users, orders, order_items, events")
    conn.close()
    print(f"[mysql] seeded ~{sum(n.values()):,} rows in {time.monotonic() - t0:.1f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scale",
        type=float,
        default=float(os.environ.get("SEED_SCALE", "1.0")),
        help="row-count multiplier (default 1.0; 0.01 for a smoke run)",
    )
    parser.add_argument("--engine", choices=["pg", "mysql", "both"], default="both")
    args = parser.parse_args()

    n = counts(args.scale)
    print(f"target rows: {n}")
    if args.engine in ("pg", "both"):
        seed_pg(n)
    if args.engine in ("mysql", "both"):
        seed_mysql(n)


if __name__ == "__main__":
    main()
