# DBDoctor

PostgreSQL + MySQL performance advisor. Customers run a single-file, read-only
collector inside their own environment; DBDoctor turns the sanitized snapshot it
produces into an evidence-backed, expert-reviewed audit report.

Companion documents: `docs/architecture.md` (system architecture),
`docs/DECISION.md` (90-day bet memo and kill criteria).

## Data flow

```
collector  ──►  engine  ──►  report
snapshot.json   Snapshot →    AnalysisResult →
(customer-run,  Findings +    HTML / PDF / tasks.md
 sanitized at   health score
 source)
```

1. **collector/** produces a normalized `snapshot.json` from PG/MySQL stat views.
2. **engine/** runs deterministic rules over the snapshot and scores the result.
3. **report/** renders findings into the customer-facing report bundle.

## Directory contracts

| Directory | Contract |
|---|---|
| `collector/` | Standalone single-file scripts a customer can audit in ~10 minutes. Stdlib + one DB driver (`psycopg` or `PyMySQL`) only — **no imports from the rest of this repo**, no writes to the target DB, literals stripped before anything leaves the customer machine. Emits Snapshot JSON. |
| `engine/` | Pure functions: `Snapshot in → AnalysisResult out`. No I/O, no network, no DB. Rules live in `engine/rules/`, all tunable thresholds in one file. |
| `report/` | Turns an `AnalysisResult` into customer-facing artifacts (HTML, PDF, tasks.md). The LLM here is a narrator only — it may not introduce numbers absent from rule evidence. |
| `webapp/backend/` | FastAPI app: auth, snapshot upload + validation, audit jobs, billing, founder review-hold. The only component that touches the app database. |
| `webapp/frontend/` | Next.js app (placeholder until Phase 4). |
| `testbed/` | Docker Compose PG15 + MySQL8 with seeded ecommerce data and a workload generator that plants known performance problems. Never points at real customer data. |
| `fixtures/` | Committed snapshot/finding JSON used by golden tests. Sanitized only. |
| `docs/` | Plans, decisions, runbooks, customer-facing enablement guides. |

## Getting started

Requires Python 3.12+ (managed via [uv](https://docs.astral.sh/uv/)) and Docker.

```bash
make setup          # create .venv with all dependency groups
make lint           # ruff check + format check
make test           # unit tests (integration tests excluded by default)

make testbed-up     # start PG15 + MySQL8 containers
make testbed-seed   # create ecommerce schema + bulk rows (SEED_SCALE=0.01 for a quick smoke run)
make testbed-load   # run the mixed problem workload (MINUTES=n to override)
```

Run the backend locally:

```bash
uv run uvicorn webapp.backend.app.main:app --reload
# GET http://127.0.0.1:8000/health  →  {"status":"ok", ...}
```
