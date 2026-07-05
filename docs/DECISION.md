# 90-Day Single-Bet Decision Memo

**Author:** Sushil · **Prepared:** 05-Jul-2026 (W0) · **Status:** DRAFT — Decision and Reason to be hand-filled by founder

This memo commits the next 90 days of side-project capacity (~10–14 hrs/week) to
exactly one bet. No parallel product work until a gate says stop or the review
date arrives.

---

## Options considered

### Option A — DBDoctor (PostgreSQL + MySQL performance advisor)

Agentless, customer-run collector → deterministic rule engine → expert-reviewed
audit report (MVP), weekly subscription report (V1). See `docs/architecture.md`
and the execution plan.

### Option B — Log-cost tool

Tooling to analyze and reduce observability/log spend.

## Evidence for each

### Option A evidence

- TODO: demand signals from network / discovery so far (fill from Phase 1 calls).
- Architecture and 20-week task plan already exist and fit solo capacity
  (199 est. hours across P0–P5 at ~12 hrs/week).
- Dual-engine scope doubles the reachable market for near-constant marginal
  cost (engine-adapter design, ~80% shared code).
- Clear paid front-door (one-time audit) before any SaaS infrastructure spend —
  revenue possible at Phase 3 with zero deployed cloud.

### Option B evidence

- TODO: fill in honestly before signing the Decision (pain observed, access to
  buyers, differentiation, time-to-first-revenue).

## Decision

> **TODO (founder, by hand):** DBDoctor / log-cost tool — one line, no hedging.

## Reason

> **TODO (founder, by hand):** the one or two decisive factors. If this
> paragraph needs more than five sentences, the decision isn't clear yet.

## Kill criteria (pre-committed gates)

Dates assume W0 = week of 06-Jul-2026. These criteria are copied from the
execution plan's Gates & Milestones and may not be re-negotiated after the fact.

| Gate | Date | Hypothesis tested | Pass criteria | Decision options |
|---|---|---|---|---|
| **Gate 1** | end W2 — **19-Jul-2026** | H1: pain + engine mix | ≥3 concrete "analyze my DB" commitments; ≥1 urgent pain; engine mix recorded | Proceed to build / +1 week outreach / shelve idea (lose 3 weeks, not 3 months) |
| **Gate 2** | end W10 — **13-Sep-2026** | H2: access model + willingness to pay | ≥2 audits delivered; ≥1 paid; ≥1 finding acted on; customer-run collector neutralized the security objection | Productize / pivot to consulting / stop before SaaS spend |
| **Gate 3** | Month 5 (≈W20+) — **22-Nov-2026** | H3: retention | ≥5 paying subscribers OR ≥2 agency accounts; acceptable month-2 churn | Scale / pivot to productized audit + agency white-label / stop |

Failing a gate means executing the listed decision option — not extending the
timeline silently.

## Review date

**30-Nov-2026** (post-Gate-3): full model review against this memo. Earlier
review only if a gate fails.
