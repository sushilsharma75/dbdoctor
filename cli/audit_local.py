"""Founder-side terminal audit: snapshot.json in, findings table out.

Usage:
    python -m cli.audit_local snapshot.json [more_snapshots.json ...]

(The customer-facing report pipeline arrives in Phase 3; this is the
quick local loop for developing rules against the testbed.)
"""

from __future__ import annotations

import json
import sys

from engine.models import Snapshot
from engine.run import run_all

SEV_ICON = {"CRITICAL": "!!", "HIGH": "! ", "MEDIUM": "~ ", "LOW": ". ", "INFO": "i "}


def print_result(path: str) -> None:
    with open(path) as f:
        snapshot = Snapshot.model_validate(json.load(f))
    result = run_all(snapshot)

    print(f"\n{'=' * 78}")
    print(
        f"{path}  ·  engine={result.engine}  ·  host={result.host_alias}"
        f"  ·  collected={result.collected_at:%Y-%m-%d %H:%M}"
    )
    deductions = ", ".join(f"{c} -{d}" for c, d in result.score.category_deductions.items() if d)
    print(f"HEALTH SCORE: {result.score.score}/100   ({deductions or 'no deductions'})")
    print(f"{'=' * 78}")

    if not result.findings:
        print("no findings")
        return
    for f in result.findings:
        print(f"{SEV_ICON[f.severity]} {f.severity:8} {f.rule_id:10} {f.affected_object[:52]}")
        ev = "  ".join(f"{k}={v}" for k, v in f.evidence.items())
        print(f"             {ev[:120]}")
    print(f"\n{len(result.findings)} findings; top issue: {result.findings[0].title}")


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    for path in args:
        print_result(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
