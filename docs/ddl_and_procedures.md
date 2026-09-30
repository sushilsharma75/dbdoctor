# DDL and stored procedure analysis

DBDoctor accepts optional PostgreSQL, MySQL and MariaDB SQL definitions alongside
an existing collector snapshot. The CLI also supports a DDL-only report. No SQL
from an uploaded file is executed, and definitions are not sent to the AI narrator.

## Use it

In **New audit**, select your snapshot and optionally select SQL files in the
**Schema and procedure DDL** field. The combined DDL limit is 5 MiB / 20 files.
Use UTF-8 plain SQL. Include the tables, indexes and routines used by the workload.

CLI with workload evidence:

```bash
uv run dbdoctor-audit --snapshot snapshot.json \
  --ddl schema.sql --ddl procedures.sql --out out/audit --skip-ai
```

Static inspection without a snapshot:

```bash
uv run dbdoctor-audit --ddl schema.sql --ddl procedures.sql \
  --engine postgres --out out/static --skip-ai --skip-pdf
```

The bundle contains `report.html`, optional `report.pdf`, `tasks.md`,
`findings.json` and, when DDL was supplied, `schema.json`. The latter records
metadata, normalized static statements and limitations. It does not retain raw
DDL bodies or literal defaults. Review source files for confidential information
before uploading: original bytes necessarily reach the server for parsing.
Object identifiers remain visible in reports. When AI narration is enabled,
only the existing finding prompt is sent; routine source bodies are not included.

API: send multipart `snapshot`, optional repeated `ddl` file parts, and
`client_alias` to `POST /jobs`. The existing ownership and review hold apply to
all artifacts, including `GET /jobs/{id}/report?fmt=schema`.

## What is analyzed

- Table columns/types, primary/unique keys, foreign-key dependencies, explicit
  indexes, MySQL inline indexes, views, and supported `ALTER TABLE ADD CONSTRAINT`.
- PostgreSQL procedures/functions with dollar-quoted SQL or PL/pgSQL bodies,
  and MySQL/MariaDB procedures/functions, including `DELIMITER` scripts.
- Named parameters and local declarations, lexical variable occurrences,
  assignment sites, loop/branch sites and dynamic SQL sites.
- Static SQL statements and direct table dependencies when the parser accepts them.
- Explicit temporary-table creation, detected columns and index declarations,
  and statement locations that read, write or drop them. `CREATE TEMP TABLE AS`
  does not infer column types or runtime row counts.
- Existing schema index keys can suppress unnecessary missing-index candidates.
  Schema metadata never fabricates index usage or changes the source database.

Routine review findings are informational. They suggest what to measure, and do
not lower the health score based on unmeasured code patterns.

## Runtime evidence

PostgreSQL collection records whether a statement is top-level, plus executor
spill blocks read/written. These are **not** sizes of user-created temporary
tables. The collector reports whether nested statement tracking is enabled.
`pg_stat_statements.track=all` is needed to observe nested statements; it does
not establish the parent routine or variable values. Outer and nested timings
can overlap. See the [PostgreSQL documentation](https://www.postgresql.org/docs/16/pgstatstatements.html).

MySQL collection optionally reads stored-program call counts, total duration and
nested-statement aggregates. Missing privileges/instrumentation produce a
capability note. An empty view does not prove routines were fast or unused.
See [MySQL statement summaries](https://dev.mysql.com/doc/mysql-perfschema-excerpt/8.0/en/performance-schema-statement-summary-tables.html).

The new PostgreSQL digest identity includes user and top-level status. After
upgrading collectors, take two new snapshots for comparable rate evidence.

## Coverage and limitations

This is conservative static inspection, not a procedural interpreter or profiler.
It does not resolve arbitrary dynamic SQL, execute branches, prove variable
scope/data flow, attribute nested SQL to a PostgreSQL routine, or infer parameter
values, plan sensitivity, temporary-table row counts or actual speedups. Unsupported
statements/languages are reported. Some syntactically accepted procedural
fragments still require human review; a parsed statement is not proof that a
routine is valid or performant.

SQL Server/T-SQL, `#temp` tables and table variables are not supported. SQL Server
needs its own collector and dialect-specific procedural analysis.

Use explicit schema/database names for exports from multiple databases. MySQL
`USE` directives establish the namespace for subsequent definitions. When a
snapshot contains exactly one table schema, unqualified uploaded definitions
use that schema; otherwise they remain unresolved. Arbitrary PostgreSQL
`search_path` changes are not evaluated. Duplicate table definitions produce a
warning. Cross-routine call graphs, MySQL executable version comments, triggers,
unsupported ALTER operations, nested variable shadowing and dynamic dependencies
are not fully resolved. Export plain CREATE definitions instead of relying on
MySQL executable comments. Full dump files can contain unsupported administrative
statements; those are reported and skipped.

A missing query/table workload yields an unavailable health score. Other missing
observation categories remain visible even when a score can be calculated.
Percentages describe captured statement time, not total database elapsed time;
collectors still cap query/table snapshots. Increasing DDL volume cannot improve
application speed by itself. Validate proposed changes against representative
parameters and execution plans, then measure latency/throughput before and after.
