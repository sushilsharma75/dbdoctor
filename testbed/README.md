# testbed/

Permanent local environment for developing and testing both collector adapters
against realistic slow-query workloads. Never contains real customer data.

## What's inside

| Service | Image | Port | Instrumentation |
|---|---|---|---|
| postgres | `postgres:15` | `15432` | `pg_stat_statements` preloaded + extension created, `track_io_timing=on` |
| mysql | `mysql:8.0` | `13306` | `performance_schema` on, statement digests enabled |

Credentials for both: user `dbdoctor` / password `dbdoctor` / database `shop`.

## Usage (from repo root)

```bash
make testbed-up      # start both containers, wait for healthchecks
make testbed-seed    # ecommerce schema + bulk rows (users/orders/order_items/events)
make testbed-load    # mixed workload, default 3 min (MINUTES=10 make testbed-load)
make testbed-down    # stop and delete volumes
```

Seeding defaults to millions of rows (~1M users, 2M orders, 4M order_items,
2M events). For a quick smoke run: `SEED_SCALE=0.01 make testbed-seed`.

## Deliberate problems planted

The seeder and workload plant known problems so collector + rule-engine output
can be verified against ground truth (used by the T2.x golden/integration tests):

| # | Problem | Where | Expected finding |
|---|---|---|---|
| P1 | Unindexed filter on `orders.customer_id` | schema (no index) + workload query | missing-index candidate (R-I1) |
| P2 | N+1 query pattern on `order_items` | workload: 1 parent + 20 child lookups per round | high-frequency query (R-Q3), later ORM rule R-O1 |
| P3 | `OFFSET 100000` pagination on `events` | workload | slow query / OFFSET anti-pattern (R-O2) |
| P4 | Long transaction holding a row lock | workload: ~8s holder + blocked waiter, every ~60s | lock wait chain (R-L1) |
| P5 | Duplicate index on `users(email)` | schema: `users_email_idx` + `users_email_dup_idx` | duplicate index (R-I3) |

## Verifying instrumentation

After `make testbed-load`, slow queries must be visible in both engines:

```bash
# PostgreSQL
docker compose -f testbed/docker-compose.yml exec postgres \
  psql -U dbdoctor -d shop -c \
  "SELECT calls, round(total_exec_time::numeric,1) AS ms, left(query,70) AS query
   FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 10;"

# MySQL
docker compose -f testbed/docker-compose.yml exec mysql \
  mysql -uroot -proot -e \
  "SELECT COUNT_STAR, ROUND(SUM_TIMER_WAIT/1e9,1) AS ms, LEFT(DIGEST_TEXT,70) AS query
   FROM performance_schema.events_statements_summary_by_digest
   WHERE SCHEMA_NAME='shop' ORDER BY SUM_TIMER_WAIT DESC LIMIT 10;"
```

The P1 full scan on `orders`, P2 high-call-count lookups, and P3 OFFSET query
should appear near the top of both lists.
