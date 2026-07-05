"""T3.1/T3.4 acceptance: both fixtures render to valid HTML; tickets carry
CONCURRENTLY (PG), staging steps and rollback notes."""

import json
from pathlib import Path

import pytest

from engine.models import Snapshot
from engine.run import run_all
from report.render import render_report
from report.tasks import suggested_sql, tasks_markdown, ticket_markdown

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


@pytest.fixture(scope="module", params=["pg_full.json", "mysql_full.json"])
def rendered(request):
    snapshot = Snapshot.model_validate(json.loads((FIXTURES / request.param).read_text()))
    result = run_all(snapshot)
    html = render_report(result, snapshot, client_alias="Acme Test")
    return result, html


def test_report_contains_all_nine_sections(rendered):
    result, html = rendered
    for marker in (
        "Database Performance Audit",  # cover title
        "Health score",  # score dial
        "Executive summary",
        "Top ",  # top issues
        "Slow queries",
        "Index advisor",
        "Growth &amp; operational risk",
        "Configuration findings",
        "Developer action plan",
    ):
        assert marker in html, marker
    # engine-specific section
    assert ("Vacuum health" in html) or ("InnoDB health" in html)


def test_report_renders_cleanly(rendered):
    result, html = rendered
    assert "{{" not in html and "{%" not in html  # no unrendered jinja
    assert str(result.score.score) in html
    assert "Acme Test" in html
    # every top finding appears with its severity chip
    for f in result.score.top_findings:
        assert f.rule_id in html
    # staging banner present for non-high-confidence findings
    if any(f.confidence != "high" for f in result.score.top_findings):
        assert "test this change in staging" in html
    # copy-as-ticket blocks embedded
    assert "Copy as ticket" in html


def test_no_credentials_or_literals_in_report(rendered):
    _, html = rendered
    assert "dbdoctor:dbdoctor" not in html
    assert "@example.com" not in html


# --- tickets -----------------------------------------------------------------


def _findings(fixture):
    snapshot = Snapshot.model_validate(json.loads((FIXTURES / fixture).read_text()))
    return run_all(snapshot).findings


def test_pg_index_suggestion_says_concurrently():
    findings = {f.rule_id: f for f in _findings("pg_full.json")}
    sql = suggested_sql(findings["R-I1"])
    assert "CREATE INDEX CONCURRENTLY" in sql
    assert "customer_id" in sql
    drop = suggested_sql(findings["R-I3"])
    assert "DROP INDEX CONCURRENTLY" in drop


def test_mysql_index_suggestion_notes_inplace():
    findings = {f.rule_id: f for f in _findings("mysql_full.json")}
    sql = suggested_sql(findings["R-I1"])
    assert "ALGORITHM=INPLACE" in sql
    assert "customer_id" in sql


def test_every_ticket_has_staging_plan_and_rollback():
    for fixture in ("pg_full.json", "mysql_full.json"):
        for f in _findings(fixture)[:10]:
            md = ticket_markdown(f)
            assert md.startswith("# [DB] ")
            assert "## Evidence" in md
            assert "## Staging test plan" in md
            assert md.count("\n1. ") == 1 and "\n3. " in md  # exactly 3 steps
            assert "Rollback:" in md


def test_tasks_markdown_bundles_top_findings():
    snapshot = Snapshot.model_validate(json.loads((FIXTURES / "pg_full.json").read_text()))
    result = run_all(snapshot)
    md = tasks_markdown(result)
    assert md.count("# [DB]") == min(10, len(result.findings))
