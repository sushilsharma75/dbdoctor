# Synthetic MySQL audit sample (Performance Schema off)

All names, SQL, counts, timestamps and resource values in this bundle are fictional. They are provided only to demonstrate the accepted DBDoctor inputs; they do not describe any real organization or database.

Upload `snapshot.json`, `slow-query.log`, `workload-metrics.json`, and `schema.sql` together in **New audit**. Choose MySQL. The snapshot explicitly records `performance_schema = OFF` and omits query statistics. The slow log supplies limited workload evidence; resource metrics show CPU, memory and connections over the same fictional period. DDL supplies table and stored procedure definitions for static inspection.

For CLI use, the snapshot and DDL can be analyzed with:

```bash
uv run dbdoctor-audit --snapshot snapshot.json --ddl schema.sql --out out/sample --skip-ai
```

The web upload also accepts the slow log and metrics as separate optional files. This sample is illustrative; the slow log only represents statements above the configured logging threshold, and the metrics are sparse snapshots rather than continuous monitoring.
