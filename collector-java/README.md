# dbdoctor JDBC collector (Java)

A read-only statistics collector for DBDoctor that connects over **JDBC** and
writes the same `snapshot.json` the Python collectors produce. It's the option
for **enterprise / Java-shop environments** where Python can't be installed but
a JVM and approved JDBC drivers already exist.

Supports **PostgreSQL**, **MySQL**, and **MariaDB**. The output is byte-for-byte
a valid DBDoctor Snapshot — the engine, report, and web app consume it unchanged
(verified: it produces the same field set as `pg_collect.py`, and DBDoctor's
rule engine scores it directly).

## What it does — and doesn't

Identical guarantees to the Python collectors:

- **Read-only.** Opens a read-only session (`default_transaction_read_only=on`
  on PostgreSQL, `SET SESSION TRANSACTION READ ONLY` on MySQL/MariaDB) and
  verifies it before collecting. Contains no INSERT/UPDATE/DELETE/DDL against
  your data.
- **Statistics views only.** Reads `pg_stat_*` / `performance_schema` /
  `information_schema` / `sys` — never your table rows.
- **Literals stripped at the source.** Every string and numeric literal is
  replaced with `?` before anything is written. No parameter values, no row
  data, no credentials reach the snapshot.
- **Hashed host alias** by default (`--keep-names` to keep readable names).
- **5-second statement timeout**, so collection can never hang your database.
- **Graceful degradation.** Missing `pg_stat_statements` or disabled
  `performance_schema` digests produce a reduced snapshot with clear notes, not
  a crash — same capability flags as the Python collectors.

## Build

Requires JDK 17+ and Maven. Produces one self-contained jar with all three JDBC
drivers bundled:

```bash
cd collector-java
mvn package
# -> target/dbdoctor-collector.jar
```

## Run

Arguments are individual (host / port / user / password / database), as
requested — no DSN string to assemble:

```bash
# PostgreSQL
java -jar target/dbdoctor-collector.jar \
  --engine postgres --host db.internal --port 5432 \
  --user dbdoctor_ro --database shop \
  --password-env DBDOCTOR_DB_PASSWORD --out snapshot.json

# MySQL
java -jar target/dbdoctor-collector.jar \
  --engine mysql --host db.internal --port 3306 \
  --user dbdoctor_ro --database shop \
  --password-env DBDOCTOR_DB_PASSWORD --out snapshot.json

# MariaDB
java -jar target/dbdoctor-collector.jar \
  --engine mariadb --host db.internal --port 3306 \
  --user dbdoctor_ro --database shop \
  --password-env DBDOCTOR_DB_PASSWORD --out snapshot.json
```

Then upload `snapshot.json` to DBDoctor exactly as you would a Python-collected
one.

### Options

| Flag | Meaning |
|---|---|
| `--engine` | `postgres` \| `mysql` \| `mariadb` (required) |
| `--host` | database host (default `127.0.0.1`) |
| `--port` | database port (default `5432` for postgres, `3306` otherwise) |
| `--user` | database user (required) |
| `--database` | database/schema to audit (required) |
| `--password` | password inline — avoid on shared hosts (see below) |
| `--password-env` | name of an env var holding the password (**preferred**) |
| `--out` | output file (default `snapshot.json`) |
| `--keep-names` | keep readable host/db names instead of hashing to an alias |
| `--selftest` | write a representative snapshot with **no** DB connection (conformance check) |
| `-h`, `--help` | usage |

### Don't put the password on the command line

`--password` is visible in the process list and shell history. Prefer
`--password-env`, which reads the password from an environment variable:

```bash
read -s -r DBDOCTOR_DB_PASSWORD; export DBDOCTOR_DB_PASSWORD
java -jar target/dbdoctor-collector.jar --engine postgres ... --password-env DBDOCTOR_DB_PASSWORD
```

## Recommended read-only grants

Same minimal, statistics-only privileges as the Python collectors:

- **PostgreSQL:** a role with the built-in `pg_monitor` membership.
  For per-query findings, enable `pg_stat_statements` (see
  `docs/enable_pg_stat_statements.md`).
- **MySQL / MariaDB:** `PROCESS`, `REPLICATION CLIENT`, and `SELECT` on
  `performance_schema` (and `sys` on MySQL). For per-query findings, enable
  `performance_schema` statement digests (see
  `docs/enable_performance_schema.md`).

## Auditability

Like the single-file Python collectors, this is meant to be read before it's
run. The entire collector is one source file —
`src/main/java/io/dbdoctor/collector/DbDoctorCollector.java` — with no logic
hidden in dependencies (the only jars bundled are the JDBC drivers). At startup
it prints the SHA256 of its own loaded `.class` so you can pin the bytecode you
ran. For the strongest assurance, build the jar yourself from this source rather
than accepting a prebuilt binary.

## Verifying conformance without a database

`--selftest` writes a fully-populated snapshot (all fields, nested lists, nulls)
without connecting anywhere. Feed it to the engine to prove the output still
matches the Snapshot schema after any change:

```bash
java -jar target/dbdoctor-collector.jar --selftest --out selftest.json
uv run python -c "import json; from engine.models import Snapshot; \
from engine.run import run_all; \
print(run_all(Snapshot.model_validate(json.load(open('selftest.json')))).score.score)"
```

## Notes

- The MySQL/MariaDB path may print a benign `SLF4J: No SLF4J providers were
  found` line to stderr (the MariaDB driver's logging facade). It does not
  affect the snapshot.
- Connecting to MySQL 8 over a non-TLS link with `caching_sha2_password` may
  require appending `?allowPublicKeyRetrieval=true&useSSL=false` semantics; use
  a TLS connection in production instead.
- Engine label follows the server: `--engine mysql` against a MariaDB server is
  still recorded as `mariadb` in the snapshot (detected from the version
  string), matching the Python collector.
