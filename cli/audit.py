"""dbdoctor-audit: one command from snapshot.json to the full report bundle.

Pipeline: validate → delta → rules → score → AI explain (guarded) →
HTML render → PDF → tasks.md → findings.json. Each stage logs its timing;
the whole bundle targets < 2 minutes.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import click

from engine.models import Snapshot
from engine.run import run_all
from report.ai_explain import AiExplainer
from report.render import render_report
from report.tasks import tasks_markdown


class _Stage:
    """Context manager logging 'stage ... done in Xs' around each step."""

    def __init__(self, name: str):
        self.name = name

    def __enter__(self):
        click.echo(f"[audit] {self.name} ...", nl=False)
        self.t0 = time.monotonic()
        return self

    def __exit__(self, exc_type, exc, tb):
        status = "failed" if exc_type else "done"
        click.echo(f" {status} in {time.monotonic() - self.t0:.1f}s")
        return False


@click.command()
@click.option(
    "--snapshot",
    "snapshot_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="snapshot.json produced by a collector",
)
@click.option(
    "--delta-of",
    "delta_path",
    type=click.Path(exists=True, dir_okay=False),
    help="older snapshot to diff against (adds growth/rate evidence)",
)
@click.option(
    "--client-alias", default="client", show_default=True, help="name shown on the report cover"
)
@click.option(
    "--out",
    "out_dir",
    default="./out",
    show_default=True,
    type=click.Path(file_okay=False),
    help="output directory for the bundle",
)
@click.option("--skip-pdf", is_flag=True, help="skip PDF generation (HTML only)")
@click.option("--skip-ai", is_flag=True, help="skip AI narration (template text only)")
@click.option(
    "--ai-model",
    default=None,
    help="Anthropic model id (default: env DBDOCTOR_AI_MODEL or claude-opus-4-8)",
)
def main(snapshot_path, delta_path, client_alias, out_dir, skip_pdf, skip_ai, ai_model) -> None:
    """Turn SNAPSHOT into report.html, report.pdf, tasks.md and findings.json."""
    t_start = time.monotonic()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    with _Stage("validate snapshot"):
        raw = json.loads(Path(snapshot_path).read_text())

    if delta_path:
        with _Stage("apply delta"):
            from collector.delta import apply_delta

            raw = apply_delta(raw, json.loads(Path(delta_path).read_text()))

    snapshot = Snapshot.model_validate(raw)

    with _Stage("run rules + score"):
        result = run_all(snapshot)
    click.echo(
        f"[audit]   engine={result.engine} findings={len(result.findings)} "
        f"score={result.score.score}/100"
    )

    ai_texts: dict[str, str] = {}
    if not skip_ai:
        with _Stage("AI explanations (digit-guarded)"):
            explainer = AiExplainer(model=ai_model, cache_dir=out / ".cache")
            ai_texts = explainer.explain_all(result.score.top_findings)

    with _Stage("render HTML"):
        html = render_report(result, snapshot, client_alias=client_alias, ai_texts=ai_texts)
        (out / "report.html").write_text(html)

    if not skip_pdf:
        with _Stage("render PDF"):
            from report.pdf import html_to_pdf

            html_to_pdf(html, out / "report.pdf")

    with _Stage("export tasks.md + findings.json"):
        (out / "tasks.md").write_text(tasks_markdown(result, ai_texts))
        (out / "findings.json").write_text(result.model_dump_json(indent=2))

    click.echo(
        f"[audit] bundle written to {out}/ in {time.monotonic() - t_start:.1f}s "
        f"({'html+pdf' if not skip_pdf else 'html only'}, tasks.md, findings.json)"
    )


if __name__ == "__main__":
    sys.exit(main())
