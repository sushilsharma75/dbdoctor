# Review hardening and administrator setup

## Administrator provisioning

Public registration always creates a regular user. `DBDOCTOR_ADMIN_EMAILS` is a
legacy setting and no longer grants privileges during registration or login.
On the trusted application host, with the same application database settings:

```bash
uv run python -m cli.admin --email reviewer@example.com
```

The command prompts for a password without displaying it. If the account already
exists, it refuses to promote it silently. Independently verify ownership before
using `--grant-existing`. Use `--revoke` to remove rights; existing tokens lose
administrative access because authorization reads the database on every request.
Audit administrators created by older versions and revoke unverified accounts.
Production startup requires a nondefault JWT secret of at least 32 characters.
Generate a cryptographically random secret and keep it outside source control.

## Security and accuracy changes

- Webhooks reject disabled billing and missing secrets. Stripe signatures expire
  after five minutes. Both providers require the expected provider, amount,
  currency, paid status and a reference before marking a payment paid.
- SQL redaction removes comments, strings (including dollar tags with digits),
  numeric literals and parameter values. Malformed lexical input is fully redacted.
  Standalone collectors include the same lexer, checked by a drift test.
- Index comparisons protect primary, unique and captured constraint indexes.
  PostgreSQL redundancy comparisons only accept plain ascending full btree keys.
  Predicates, included columns, expressions, special ordering/operator classes
  and other methods are excluded. Prefix overlap is a medium-confidence candidate;
  compare workload plans and usage before removing an index.
- Missing-index candidates resolve aliases and qualified objects using a SQL AST.
  Ambiguous unqualified names and unresolved derived-table lineage yield no advice.
  Generated index SQL preserves schema qualification and quotes identifiers.
- Missing query/table observations produce an unavailable score. Reports list
  coverage. High mean latency does not imply every execution was slow.
- Snapshot reads and DDL inputs are bounded. Raw uploaded snapshot SQL is redacted
  again before persistence; raw DDL files are not written to the job directory.

Payments remain off by default. The existing checkout provider adapter still
needs a real provider implementation before accepting live payments. This change
hardens verification; it does not configure a merchant account or deploy anything.
