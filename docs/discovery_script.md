# Discovery call script — 8 questions (T0.4)

> ~20 minutes. Listen 80%, talk 20%. Capture verbatim pain quotes.
> Fill `docs/call_notes_template.md` immediately after each call.
> Drafted from the task plan (Q1 = engine mix per T0.4 acceptance);
> review against docs/plan.md Phase 1 when available.

**Q1 — Engine mix.** "What databases are you running in production —
PostgreSQL, MySQL/MariaDB, something else? Managed (RDS/Cloud SQL) or
self-hosted? Roughly what size?"
*(Records the engine-mix evidence Gate 1 requires.)*

**Q2 — Last incident.** "Tell me about the last time the database made your
app slow or caused an incident. What happened, and how did you find out?"

**Q3 — Current practice.** "Who looks at database performance today? What do
they use — APM, slow query log, gut feel, nothing?"

**Q4 — Time cost.** "Roughly how much dev time went into DB performance
issues in the last quarter? What did that displace?"

**Q5 — Money cost.** "Have you upgraded the instance size to make a problem
go away? What does the DB cost you per month now?"

**Q6 — Access model (H2 test).** "If someone offered to analyze your
production DB, what would you need to trust them? How would you feel about
running a small read-only script yourself and uploading the sanitized
output — versus giving them a connection string?"
*(Listen carefully — this tests the core access-model hypothesis.)*

**Q7 — Willingness to pay.** "If a report told you exactly which queries,
indexes, and settings to fix, prioritized, with evidence — what would that
be worth? One-time or ongoing?"

**Q8 — Commitment (Gate 1).** "I'm running the first audits now. Would you
run the collector on one of your databases and let me analyze it? Which one?"
*(A named database = a commitment. 'Sounds interesting' does not count.)*

## After the call

1. Normalize notes into the template (paste raw notes into Claude chat).
2. Update `prospects.csv` status + next action.
3. File as `docs/discovery/YYYY-MM-DD_<name>.md`.
