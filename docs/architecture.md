# DBDoctor — Architecture Document
## PostgreSQL + MySQL Performance Advisor SaaS

**Version:** 1.0 · **Date:** 03-Jul-2026 · **Author:** Sushil (solo founder/architect)
**Companion documents:** `dbdoctor_execution_plan.md` (business/phase plan), `dbdoctor_task_plan.xlsx` (task-level build plan)
**Status:** Approved for MVP build (Phases 2–3); V1 sections marked accordingly

---

## 1. Purpose, Scope, and Architectural Goals

DBDoctor analyzes production PostgreSQL and MySQL databases and delivers prioritized, plain-English performance findings as an expert-reviewed audit report (MVP) and a weekly subscription report (V1). This document defines the system architecture, component contracts, data model, security model, and the design decisions behind them.

**Architectural goals, in priority order:**

| # | Goal | Consequence in the design |
|---|---|---|
| A1 | **Trust: never hold customer credentials or raw data** | Agentless customer-run collectors; sanitization at source; upload-only ingestion |
| A2 | **Solo-maintainable at 10–14 hrs/week** | Modular monolith, one deploy unit, boring technology, ~80% code shared across engines |
| A3 | **Dual-engine (PG + MySQL) without 2× cost** | Engine-adapter pattern converging on one normalized schema; rules are engine-agnostic where possible |
| A4 | **Report-first product** (no real-time promises) | Batch pipeline architecture; no streaming, no agents, no always-on connections in MVP |
| A5 | **Findings must be evidence-backed and defensible** | Deterministic rule engine produces facts; LLM only narrates them (grounding guard) |
| A6 | **Human-in-the-loop quality** | Review-hold workflow: no report reaches a customer unapproved in MVP |

**Explicit non-goals (by design, see plan §5):** real-time dashboards, APM/tracing correlation, auto-applying any change to customer databases, per-minute monitoring/alerting, log tailing.

---

## 2. System Context (C4 Level 1)

```text
                       CUSTOMER ENVIRONMENT (trust boundary A)
  ┌─────────────────────────────────────────────────────────────┐
  │  PostgreSQL / MySQL          dbdoctor collector script       │
  │  (production DB) ◄──SQL,     (customer-run, single file,     │
  │   read-only user   SELECT──  auditable, sanitizes at source) │
  │                    only)              │                      │
  └───────────────────────────────────────┼──────────────────────┘
                                          │ snapshot.json (HTTPS upload,
                                          │ normalized SQL, no credentials)
                       DBDOCTOR CLOUD (trust boundary B)
  ┌───────────────────────────────────────▼──────────────────────┐
  │  Web App (Next.js) ── API (FastAPI) ── Job Queue ── Pipeline: │
  │  Auth · Billing        validation      worker      rules →    │
  │  Dashboard             schema-check                score →    │
  │                                                    AI explain→│
  │  Founder review UI ◄── review-hold ◄──────────────report gen  │
  └───────────────┬──────────────────────────────┬───────────────┘
                  │                              │
        Anthropic API (LLM,            Razorpay / Stripe (payments)
        evidence-only prompts)         Email (SES/Resend)
                  │
  ┌───────────────▼──────────────────────────────────────────────┐
  │  CUSTOMER: PDF report + tasks.md + weekly email (V1)          │
  └──────────────────────────────────────────────────────────────┘
```

**Actors:** Customer developer/CTO (runs collector, receives reports), Agency admin (V1: manages client portfolio), Founder (reviews every report pre-delivery, tunes thresholds).

**The defining boundary decision:** trust boundary A is never crossed by DBDoctor infrastructure in the MVP. All database access happens inside the customer's environment, executed by the customer, with output they can inspect before uploading. Hosted collection (crossing boundary A with explicit consent) is a V1 opt-in only.

---

## 3. Component Architecture (C4 Level 2)

### 3.1 Component map

```text
dbdoctor/ (monorepo, one deployable backend + static frontend)
│
├── collector/            [runs in CUSTOMER env — shipped as single files]
│   ├── pg_collect.py         PG adapter → Snapshot JSON
│   ├── mysql_collect.py      MySQL/MariaDB adapter → Snapshot JSON
│   ├── delta.py              two-snapshot diffing (growth, rates)
│   └── log_sanitize.py       [V1.5] optional slow-log sanitizer
│
├── engine/               [pure functions — no I/O, no DB, no network]
│   ├── models.py             Snapshot schema (the system's central contract)
│   ├── rules/                25–30 rule classes + registry
│   ├── plan_check.py         [V1] EXPLAIN validation of index suggestions
│   ├── score.py              health score rollup
│   └── run.py                run_all(Snapshot) → AnalysisResult
│
├── report/
│   ├── render.py             AnalysisResult → HTML (Jinja2)
│   ├── pdf.py                HTML → PDF (Playwright/Chromium)
│   ├── ai_explain.py         LLM narration w/ grounding guard + cache
│   ├── tasks.py              findings → Jira/GitHub-ready tickets
│   └── cost_frame.py         [V1] fix-vs-upgrade framing
│
├── webapp/
│   ├── backend/              FastAPI: auth, jobs, billing, review-hold,
│   │                         orgs/clients [V1], scheduler [V1], alerts [V1]
│   └── frontend/             Next.js: landing, wizard, dashboard,
│                             founder review UI, agency portfolio [V1]
│
├── cli/audit.py          founder-side end-to-end pipeline runner
└── testbed/              Docker: PG15 + MySQL8 + MariaDB + seeded workloads
```

### 3.2 The engine-adapter pattern (core of goal A3)

Both collectors emit the **same normalized `Snapshot` JSON**. Everything downstream — rules, scoring, AI, reports, storage — is engine-agnostic and consumes only this schema. Engine knowledge lives in exactly two places: the collector (source mapping) and a small set of engine-tagged rules.

| Normalized field | PostgreSQL source | MySQL source |
|---|---|---|
| QueryStat | `pg_stat_statements` | `events_statements_summary_by_digest` |
| TableStat | `pg_stat_user_tables`, `pg_relation_size` | `information_schema.tables`, sys full-scan views |
| IndexStat | `pg_stat_user_indexes` + indexdef parse | `sys.schema_unused_indexes`, `sys.schema_redundant_indexes` |
| LockWait | `pg_locks` ⋈ `pg_stat_activity` | `sys.innodb_lock_waits` |
| ConnectionInfo | `pg_stat_activity` vs `max_connections` | status vars vs `max_connections` |
| ConfigSetting | `pg_settings` whitelist | `SHOW GLOBAL VARIABLES/STATUS` whitelist |
| Extra per engine | dead tuples, vacuum stats | rows_examined/sent, buffer pool, `data_free`, p95/p99 quantiles |

Fields not available on one engine are nullable; rules declare which fields they require and skip gracefully. Adding a third engine later (e.g., MariaDB-specific or SQL Server) means one new collector + a handful of rules — nothing downstream changes.

### 3.3 Rule engine design

- Rules are **pure functions**: `evaluate(Snapshot) → list[Finding]`. No I/O. This makes them trivially unit-testable (golden fixtures), reorderable, and safe to run anywhere.
- `Finding` = rule_id, severity (CRITICAL→INFO), **evidence** (named numeric facts — the audit's credibility), affected_object, suggested_action, confidence (high/medium/low), engine.
- All thresholds live in a single `thresholds.py` dataclass — tuning from real audit feedback is a one-file change (plan risk: false positives erode trust).
- Severity → health score via a deterministic capped rollup (`score.py`): no category can zero the score alone; property-tested for monotonicity.

### 3.4 AI layer — deliberately thin

The LLM is a **narrator, not an analyst** (goal A5). Per finding: one API call, prompt contains only the rule title + evidence dict + engine; system prompt forbids numbers not in evidence and forbids performance promises. A **digit-guard** post-validates output (any digit absent from evidence ⇒ reject, retry once, fall back to the rule's template text). Responses cached by finding-hash; the whole product works offline with template text if the API is down. This keeps the "real IP" in the deterministic rules, exactly as the plan requires.

### 3.5 Report pipeline

```text
snapshot.json ─► validate(schema) ─► delta(prev) ─► rules ─► score
     ─► ai_explain (guarded) ─► HTML render ─► PDF + tasks.md + findings.json
     ─► REVIEW HOLD (founder approves in UI) ─► customer download / email
```

Synchronous, idempotent, restartable per stage; each stage logs timing. Target: full bundle < 2 minutes. MVP runs it in a FastAPI background worker; the V1 subscription scheduler reuses the identical pipeline on a weekly cron per database — one pipeline, two triggers.

---

## 4. Data Architecture

### 4.1 Entity model (application Postgres)

```text
User ──< Organization [V1] ──< Client [V1] ──< DatabaseTarget
                                                   │
User ──< AuditJob (engine, status, paid,           ├──< SnapshotSeries
         review_state, report_path) ── Payment     │      (26 weekly snapshots,
                                        (+GST inv) │       counters + deltas)
                                                   └──< ReportArchive
```

- **MVP entities:** User, AuditJob, Payment. **V1 adds:** Organization/Client/DatabaseTarget hierarchy (agency workspace), SnapshotSeries, ReportArchive, AlertSettings.
- Snapshots stored as compressed JSON blobs (object storage / disk) referenced by row — they are already small (top-200 queries, top-100 relations), typically < 2 MB.
- Authorization is **org-scoped at the query layer** — every ORM query filters by org; cross-org isolation is covered by dedicated tests (agency data = multiple end-clients' metadata in one account, the highest-sensitivity area).

### 4.2 Data classification & lifecycle

| Data | Classification | Handling |
|---|---|---|
| Normalized SQL digests, metric counters | Low-sensitivity (literals stripped at source) | Stored 26 weeks (series) / 12 months (audit bundles), then deleted |
| Customer DB hostnames/dbnames | Medium | Hashed to `host_alias` by default in the collector |
| Customer credentials | **Never stored in MVP.** V1 hosted mode only: encrypted at rest (KMS/libsodium), opt-in, deletable | |
| Reports (PDF) | Customer-confidential | Signed expiring URLs; watermarked with client alias |
| Payment data | Delegated | Stripe/Razorpay hold card data; we store only references + GST invoice records |

---

## 5. Security Architecture

**Threat model priorities:** (1) we must be a low-value breach target — achieved by never holding credentials or raw SQL; (2) agency tenant isolation; (3) supply-chain trust in the collector customers execute.

Controls:

1. **Collector trust:** single-file, dependency-minimal (psycopg/PyMySQL only), human-readable in ~10 minutes, prints its own SHA256 at run; distributed with published checksums. Opens the DB session read-only (`default_transaction_read_only=on` / read-only session), and the code contains no write statements to find.
2. **Least privilege at the source:** documented grants are `pg_monitor` (PG) and PROCESS/REPLICATION CLIENT + SELECT on `performance_schema`/`sys` (MySQL) — statistics views only, no table data.
3. **Sanitization at source:** literal stripping happens inside the customer's environment before any byte leaves it (MySQL digests arrive pre-normalized; PG gets a defense-in-depth regex pass). Server-side, uploads are schema-validated and size-capped before acceptance.
4. **Platform basics:** TLS everywhere, JWT auth with short expiry, admin/review endpoints role-gated, rate-limited uploads, dependency scanning in CI, no customer data in logs.
5. **AI boundary:** only evidence dicts (numbers + object names) are sent to the LLM — never full snapshots, never anything that could contain a literal.

---

## 6. Deployment Architecture

**MVP → early revenue (₹0–50k MRR): one VPS, Docker Compose.**

```text
Single VM (Hetzner/DO, 4 vCPU/8GB)
 ├─ caddy (TLS) ─► frontend (Next.js) + api (FastAPI)
 ├─ worker (same image, queue consumer)  ├─ postgres:15 (app DB)
 ├─ redis (queue/cache)                  └─ volumes: snapshots/, reports/
Backups: nightly pg_dump + snapshot dir → object storage. IaC: one compose file + Makefile.
```

Rationale: goal A2. A report-batch product has no bursty load; the heaviest job (Playwright PDF) is seconds. One machine, one compose file, restore-from-backup DR (RTO hours, acceptable for a weekly-cadence product — stated honestly in SLAs).

**Scale path (only when forced):** move object storage out → managed Postgres → split worker to second VM → K8s never, unless the company looks completely different. Each step is enabled, not required, by the current design (stateless api/worker, queue in the middle).

---

## 7. Key Design Decisions (ADR summary)

| # | Decision | Alternatives rejected | Why |
|---|---|---|---|
| ADR-1 | Agentless customer-run collector | Installed agent (Releem/pganalyze model); hosted connection | H2 (access trust) is the #1 deal risk; also removes agent maintenance burden (A1, A2). Costs us continuous data — acceptable for report cadence (A4). |
| ADR-2 | Stats views, not log files, as primary source | Slow-log parsing (pgBadger model) | Complete + pre-aggregated + PII-free + works on RDS/Cloud SQL. Log-only outliers handled by stddev/p99 rules; optional sanitized log ingestion parked at V1.5 (T5.12). |
| ADR-3 | Normalized Snapshot schema; adapters at the edge | Per-engine pipelines | 70–80% shared code across engines (A3); third engine = one adapter. |
| ADR-4 | Deterministic rules + LLM-as-narrator with digit-guard | LLM analyzes raw metrics | Findings must be reproducible and defensible (A5); no hallucinated numbers in a paid expert report; offline fallback. |
| ADR-5 | Modular monolith, one deploy unit | Microservices, serverless | Solo founder (A2). Module boundaries (collector/engine/report/webapp) preserve future extraction. |
| ADR-6 | Review-hold before delivery | Fully automated delivery | G10: founder judgment is the product early; protects trust while thresholds are tuned; removed gradually after ~20 reports. |
| ADR-7 | Postgres for app data + JSON blobs for snapshots | Timeseries DB (Timescale/Clickhouse) | Weekly cadence × 26 snapshots × small blobs ≠ a timeseries problem yet. Revisit at thousands of databases. |
| ADR-8 | `EXPLAIN` only, never `EXPLAIN ANALYZE`, opt-in, top-10 queries [V1] | Continuous auto_explain capture | Zero execution risk on customer prod; auto_explain requires log access we chose not to need (ADR-2). |

---

## 8. Non-Functional Requirements

| NFR | Target | Mechanism |
|---|---|---|
| Audit pipeline latency | < 2 min snapshot→bundle (excl. human review) | Measured per stage; fixture perf test in CI |
| Collector runtime impact | < 5 s, read-only, no locks taken | Stat-view SELECTs only; statement_timeout set |
| Availability | 99% business-hours (stated honestly; weekly-cadence product) | Single VM + backups; status page |
| Report correctness | Zero invented numbers; every finding evidence-backed | Digit-guard tests; golden-fixture rule tests; review-hold |
| Tenant isolation [V1] | No cross-org access | Org-scoped queries + dedicated authz test suite |
| Cost to serve | < ₹8k/month infra until Gate 3 | One VM, cached LLM calls, no idle GPU/streaming infra |

---

## 9. Architecture Roadmap by Phase

| Phase | Architecture delivered |
|---|---|
| P2 (W3–8) | Collectors (both engines), Snapshot schema, rule engine + score — all runnable via CLI, no cloud needed |
| P3 (W9–10) | Report pipeline (HTML/PDF/AI/tasks), founder CLI; **first revenue with zero deployed infrastructure** |
| P4 (W11–13) | Web app, auth, upload+validation, billing+GST, review-hold — the compose stack goes live |
| P5 (W14–20) | Scheduler + SnapshotSeries, regression rules, agency/org model, white-label rendering, EXPLAIN validation, alerts |
| V1.5+ | Optional sanitized slow-log ingestion (T5.12); hosted collector opt-in; schema pre-flight tool |

Note the deliberate property of P2–P3: the entire analytical core is built and sold (as hand-run audits) **before any cloud architecture exists**. The SaaS layer wraps a working, revenue-validated pipeline — not the other way around.
