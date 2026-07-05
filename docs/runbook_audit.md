# Runbook: delivering an audit (founder-side, Phase 3)

One customer snapshot in, one reviewed report bundle out. Target: < 30 min of
founder time per audit, < 2 min of pipeline time.

## 1. Customer runs the collector

Send the customer the dist artifact (`make dist` → `dist/pg_collect.py` or
`dist/mysql_collect.py`) plus its published SHA256. They run:

```bash
python pg_collect.py --dsn postgresql://readonly_user:...@host/db --out snapshot.json
```

and send back `snapshot.json` (≈ a few hundred KB, literals stripped at
source). If they can run it twice ~24h apart, ask for both files — the delta
adds growth and call-rate evidence.

## 2. Generate the bundle

```bash
export ANTHROPIC_API_KEY=...   # optional; omit for template-text narration
uv run dbdoctor-audit \
    --snapshot snapshot.json \
    --delta-of snapshot_day_before.json \   # optional
    --client-alias "Acme Pvt Ltd" \
    --out out/acme-2026-07-05
```

Outputs in the bundle directory:

| File | Purpose |
|---|---|
| `report.pdf` | The deliverable (A4, watermarked footer) |
| `report.html` | Same content for quick browser review |
| `tasks.md` | Paste-ready GitHub/Jira tickets for the top findings |
| `findings.json` | Raw `AnalysisResult` for your records / regression checks |

Flags: `--skip-pdf` (HTML only), `--skip-ai` (deterministic template text),
`--ai-model` (default `claude-opus-4-8`, or env `DBDOCTOR_AI_MODEL`).

## 3. Review before sending (G10 — non-negotiable in MVP)

Read every Top-5 card and ask, per finding:

1. Is the evidence sufficient for the claim? (Numbers in the paragraph MUST
   appear in the evidence table — the digit guard enforces this, verify anyway.)
2. Is the severity defensible to a skeptic?
3. Would the suggested action be safe on THIS customer's stack?

Cut or downgrade anything you wouldn't defend on a call. Then send the PDF +
`tasks.md` and book the 30-minute debrief (T3.6).

## 4. Troubleshooting

- **"collection failed"** from the customer: usually missing grants — point
  them at `docs/enable_pg_stat_statements.md` / `docs/enable_performance_schema.md`.
- **Empty queries section**: snapshot was taken without query stats; the
  report says so honestly. Ask them to enable stats and re-run tomorrow.
- **PDF generation fails**: `uv run playwright install chromium` once per
  machine (the HTML report is always written regardless).
- **AI narration missing**: no `ANTHROPIC_API_KEY` or API down — the bundle
  still ships with rule template text; this is by design.
