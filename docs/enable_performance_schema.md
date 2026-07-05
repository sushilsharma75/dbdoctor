# Enabling performance_schema statement digests (MySQL / MariaDB)

The dbdoctor collector reads per-query statistics from
`performance_schema.events_statements_summary_by_digest`. On MySQL 5.7/8.0
this is **on by default** — you usually don't need to do anything. This guide
covers the cases where it isn't.

Digest statistics store **normalized** statements (literals already replaced
by `?`), so enabling them does not record query parameter values anywhere.

## Check current state

```sql
SELECT @@performance_schema;                       -- must be 1
SELECT NAME, ENABLED FROM performance_schema.setup_consumers
 WHERE NAME = 'statements_digest';                 -- must be YES
```

The collector runs this same check itself and prints the exact fix if
anything is off.

## Fix 1 — consumers disabled (no restart needed)

```sql
UPDATE performance_schema.setup_consumers
   SET ENABLED = 'YES'
 WHERE NAME IN ('statements_digest', 'global_instrumentation',
                'thread_instrumentation');
```

## Fix 2 — performance_schema off entirely (restart needed)

Add to `my.cnf` under `[mysqld]`, then restart:

```ini
performance_schema = ON
performance-schema-consumer-statements-digest = ON
```

On managed platforms set the equivalent parameter:

- **Amazon RDS / Aurora MySQL:** set `performance_schema = 1` in the DB
  parameter group and reboot.
- **Google Cloud SQL for MySQL:** `gcloud sql instances patch INSTANCE
  --database-flags=performance_schema=on`

## MariaDB notes

- On MariaDB, `performance_schema` is **OFF by default** — Fix 2 is almost
  always required.
- The `sys` schema advisor views (`schema_unused_indexes`,
  `schema_redundant_indexes`, full-scan views) do not ship with MariaDB.
  The collector detects this, continues with reduced capabilities, and notes
  it in the snapshot — index findings are then derived from index
  definitions downstream with reduced confidence.
- Statement latency percentiles (p95/p99) are MySQL 8 only.

## Recommended grants for the collector account

```sql
CREATE USER 'dbdoctor_ro'@'%' IDENTIFIED BY '...';
GRANT PROCESS, REPLICATION CLIENT ON *.* TO 'dbdoctor_ro'@'%';
GRANT SELECT ON performance_schema.* TO 'dbdoctor_ro'@'%';
GRANT SELECT ON sys.* TO 'dbdoctor_ro'@'%';          -- MySQL only
GRANT EXECUTE ON sys.* TO 'dbdoctor_ro'@'%';         -- sys views call sys functions
```

Statistics views only — the account never needs SELECT on your data.

## Afterwards

Let your normal workload run for at least a day so statistics accumulate,
then re-run the collector:

```bash
python mysql_collect.py --dsn mysql://... --out snapshot.json
```

The collector's startup output should now include `query_stats` in its
capabilities list.
