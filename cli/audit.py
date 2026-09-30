"""dbdoctor-audit: one command from snapshot.json to the full report bundle.

Pipeline: validate → delta → rules → score → AI explain (guarded) →
HTML render → PDF → tasks.md → findings.json. Each stage logs its timing;
the whole bundle targets < 2 minutes.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
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
    required=False,
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
@click.option(
    "--ddl",
    "ddl_paths",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Optional DDL file; repeat for related schemas (20 files / 5 MiB total).",
)
@click.option(
    "--engine",
    type=click.Choice(["postgres", "mysql", "mariadb"]),
    help="Required for DDL-only analysis without a snapshot.",
)
@click.option("--skip-pdf", is_flag=True, help="skip PDF generation (HTML only)")
@click.option("--skip-ai", is_flag=True, help="skip AI narration (template text only)")
@click.option(
    "--ai-model",
    default=None,
    help="Anthropic model id (default: env DBDOCTOR_AI_MODEL or claude-opus-4-8)",
)
def main(
    snapshot_path, delta_path, client_alias, out_dir, skip_pdf, skip_ai, ai_model, ddl_paths, engine
) -> None:
    """Turn SNAPSHOT into report.html, report.pdf, tasks.md and findings.json."""
    if not snapshot_path and not (ddl_paths and engine):
        raise click.UsageError("Provide --snapshot, or --ddl with --engine for static analysis.")
    if delta_path and not snapshot_path:
        raise click.UsageError("--delta-of requires --snapshot")
    t_start = time.monotonic()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    with _Stage("validate snapshot"):
        raw = (
            json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
            if snapshot_path
            else {
                "meta": {
                    "engine": engine,
                    "version": "ddl-1",
                    "host_alias": "ddl-only",
                    "collected_at": datetime.now(UTC).isoformat(),
                }
            }
        )

    if delta_path:
        with _Stage("apply delta"):
            from collector.delta import apply_delta

            raw = apply_delta(raw, json.loads(Path(delta_path).read_text(encoding="utf-8")))

    snapshot = Snapshot.model_validate(raw)
    if engine and snapshot.meta.engine != engine:
        raise click.UsageError("--engine does not match the snapshot")
    if ddl_paths:
        from engine.ddl import MAX_DDL_BYTES, MAX_DDL_FILES, ingest_ddl

        if len(ddl_paths) > MAX_DDL_FILES:
            raise click.UsageError("At most 20 DDL files are supported")
        sources, remaining = [], MAX_DDL_BYTES
        try:
            for path in ddl_paths:
                with Path(path).open("rb") as stream:
                    data = stream.read(remaining + 1)
                remaining -= len(data)
                if remaining < 0:
                    raise ValueError("DDL exceeds 5 MiB combined")
                sources.append(data.decode("utf-8-sig"))
            schemas = {t.schema_name for t in snapshot.tables}
            default_schema = next(iter(schemas)) if len(schemas) == 1 else None
            snapshot.schema_catalog = ingest_ddl(sources, snapshot.meta.engine, default_schema)
        except (ValueError, UnicodeDecodeError) as exc:
            raise click.ClickException(str(exc)) from None

    with _Stage("run rules + score"):
        result = run_all(snapshot)
    score_label = f"{result.score.score}/100" if result.score.score is not None else "unavailable"
    click.echo(
        f"[audit]   engine={result.engine} findings={len(result.findings)} score={score_label}"
    )

    ai_texts: dict[str, str] = {}
    if not skip_ai:
        with _Stage("AI explanations (digit-guarded)"):
            explainer = AiExplainer(model=ai_model, cache_dir=out / ".cache")
            ai_texts = explainer.explain_all(result.score.top_findings)

    with _Stage("render HTML"):
        html = render_report(result, snapshot, client_alias=client_alias, ai_texts=ai_texts)
        (out / "report.html").write_text(html, encoding="utf-8")

    if not skip_pdf:
        with _Stage("render PDF"):
            from report.pdf import html_to_pdf

            html_to_pdf(html, out / "report.pdf")

    with _Stage("export tasks.md + findings.json"):
        (out / "tasks.md").write_text(tasks_markdown(result, ai_texts), encoding="utf-8")
        if result.schema_catalog:
            (out / "schema.json").write_text(
                result.schema_catalog.model_dump_json(indent=2), encoding="utf-8"
            )
        (out / "findings.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")

    click.echo(
        f"[audit] bundle written to {out}/ in {time.monotonic() - t_start:.1f}s "
        f"({'html+pdf' if not skip_pdf else 'html only'}, tasks.md, findings.json)"
    )


if __name__ == "__main__":
    sys.exit(main())
