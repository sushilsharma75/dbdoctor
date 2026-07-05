# Enabling pg_stat_statements

`pg_stat_statements` is PostgreSQL's built-in per-statement statistics
extension. The dbdoctor collector works without it, but per-query findings —
the most valuable part of the audit — need it. It ships with PostgreSQL, adds
negligible overhead, and is widely run in production.

It stores **normalized** statements (literals already replaced by `$1`, `$2`),
so enabling it does not put query parameter values anywhere.

## Amazon RDS / Aurora PostgreSQL

1. In the instance's **DB parameter group**, set:
   ```
   shared_preload_libraries = 'pg_stat_statements'
   ```
   (On many RDS engine versions it is already preloaded — check first.)
2. Reboot the instance (required for `shared_preload_libraries` changes).
3. In your database, run once:
   ```sql
   CREATE EXTENSION pg_stat_statements;
   ```

## Google Cloud SQL

1. Set the flag (triggers a restart):
   ```bash
   gcloud sql instances patch INSTANCE_NAME \
     --database-flags=shared_preload_libraries=pg_stat_statements
   ```
2. Then in your database:
   ```sql
   CREATE EXTENSION pg_stat_statements;
   ```

## Self-hosted

1. In `postgresql.conf`:
   ```
   shared_preload_libraries = 'pg_stat_statements'
   ```
2. Restart PostgreSQL.
3. In your database:
   ```sql
   CREATE EXTENSION pg_stat_statements;
   ```

## Afterwards

Let your normal workload run for at least a day so statistics accumulate,
then re-run the collector:

```bash
python pg_collect.py --dsn postgresql://... --out snapshot.json
```

The collector's startup output should now include `query_stats` in its
capabilities list.

## Optional: track_io_timing

For I/O-timing evidence in future audits (small measurement overhead,
generally safe on modern hardware):

```sql
ALTER SYSTEM SET track_io_timing = on;
SELECT pg_reload_conf();
```
