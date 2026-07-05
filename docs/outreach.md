# Outreach messages (T0.4)

> Drafted from the architecture doc and task plan; `docs/plan.md` (execution
> plan) was not in the repo when these were written — review against it and
> edit for your own voice before sending. Every variant must keep two facts:
> **read-only** and **you run the script, we never get credentials**.

## Variant 1 — cold CTO (small SaaS)

> Hi {name} — I'm building DBDoctor, a performance audit for production
> Postgres/MySQL. You run a single read-only script (it's ~400 lines, you can
> read it first; we never get credentials or data — only normalized stats).
> You get back a prioritized report: slow queries, missing/duplicate indexes,
> config problems, each with evidence and a dev-ready fix. I'm doing the
> first audits hands-on with a few CTOs. If your DB is slower than it should
> be, want me to take a look?

## Variant 2 — agency owner

> Hi {name} — quick question for you as an agency owner: when a client's
> site slows down, who checks the database? I'm building DBDoctor — a DB
> performance audit you can run across client projects (Postgres + MySQL).
> One read-only script per client, no credentials shared, and you get a
> white-label-able report with prioritized fixes your devs can action. Would
> a portfolio-wide DB health check be useful to you? Happy to audit one
> client site free to show the output.

## Variant 3 — warm network

> Hey {name} — I'm finally building something of my own: DBDoctor, database
> performance audits for Postgres/MySQL (slow queries, indexes, config —
> evidence-backed report, customer-run read-only collector so I never touch
> prod). I'm looking for 15–20 people running production DBs to sanity-check
> the idea with a 20-min chat — not selling, genuinely researching. Know
> your setup qualifies. Can I steal 20 minutes this week?

## Rules of engagement

- Under 90 words each; personalize the first line per prospect.
- Always mention: read-only, customer-run, no credentials.
- The goal of the reply is a **call**, not a sale.
- Log every send + reply in `prospects.csv`.
