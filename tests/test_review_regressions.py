"""Regression cases discovered in the senior review."""

from pathlib import Path

import pytest

from collector.mysql_collect import normalize_sql as mysql_normalize
from collector.pg_collect import normalize_sql
from engine.rules.index_rules import DuplicateIndex, MissingIndexCandidate
from engine.run import run_all
from engine.sql_analysis import filter_candidates
from engine.sql_lexer import redact_sql
from report.render import render_report
from report.tasks import suggested_sql
from tests.rules.conftest import MB, make_index, make_query, make_snapshot, make_table


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT $tag1$private_token$tag1$",
        "SELECT 1 /* customer_email=private_token /* nested */ more */",
        "SELECT 1 -- private_token\n",
        "SELECT 'private_token",
        "SELECT $tag1$private_token",
    ],
)
def test_pg_redaction_fails_closed(sql):
    assert "private_token" not in normalize_sql(sql)
    assert normalize_sql(sql) == redact_sql(sql)


def test_mysql_redaction_and_identifier_preservation():
    assert "private_token" not in mysql_normalize('SELECT "private_token" # private_token\n')
    assert "`col1`" in mysql_normalize("SELECT `col1` FROM `t2` WHERE id=10")
    assert "private_token" not in mysql_normalize("SELECT 1 /*! private_token */")
    assert '"MixedCase"' in normalize_sql('SELECT "MixedCase" FROM t WHERE a=1')


def test_standalone_lexers_match_shared_source():
    def block(path):
        return (
            Path(path)
            .read_text()
            .split("# BEGIN SHARED SQL LEXER")[1]
            .split("# END SHARED SQL LEXER")[0]
        )

    assert block("engine/sql_lexer.py") == block("collector/pg_collect.py")
    assert block("engine/sql_lexer.py") == block("collector/mysql_collect.py")


@pytest.mark.parametrize(
    "definition",
    [
        "CREATE INDEX idx ON public.t USING btree (email) WHERE active",
        "CREATE INDEX idx ON public.t USING hash (email)",
        "CREATE INDEX idx ON public.t USING btree (email) INCLUDE (name)",
        "CREATE INDEX idx ON public.t USING btree (email DESC)",
        "CREATE INDEX idx ON public.t USING btree (lower(email))",
        "CREATE INDEX idx ON public.t USING btree (email text_pattern_ops)",
    ],
)
def test_special_indexes_never_cover_plain_index(definition):
    snapshot = make_snapshot(
        indexes=[
            make_index(name="a_special", definition=definition),
            make_index(
                name="z_full", definition="CREATE INDEX z_full ON public.t USING btree (email)"
            ),
        ]
    )
    assert not DuplicateIndex().evaluate(snapshot)


def test_unique_prefix_never_recommended_for_drop():
    snapshot = make_snapshot(
        indexes=[
            make_index(name="a_unique", definition="(email)", is_unique=True),
            make_index(name="longer", definition="(email, status)"),
        ]
    )
    assert not DuplicateIndex().evaluate(snapshot)


def test_schema_alias_and_join_filter_resolution():
    candidates = dict(
        filter_candidates(
            "SELECT * FROM sales.orders o JOIN auth.users u ON o.user_id=u.id "
            "WHERE o.status=? AND u.email=?"
        )
    )
    assert candidates == {"sales.orders": ("status",), "auth.users": ("email",)}
    assert not filter_candidates("SELECT * FROM a JOIN b ON a.id=b.id WHERE status=?")
    assert not filter_candidates("SELECT * FROM a WHERE status=? OR kind=?")
    # Derived columns require lineage, so skip the outer filter rather than invent a base column.
    assert not filter_candidates(
        "WITH x AS (SELECT count(*) AS n FROM t) SELECT * FROM x WHERE n=?"
    )


def test_qualified_tables_do_not_mix_schemas():
    snapshot = make_snapshot(
        tables=[
            make_table(schema_name="sales", name="orders", size_bytes=200 * MB, seq_scans=1000),
            make_table(schema_name="archive", name="orders", size_bytes=200 * MB, seq_scans=1000),
        ],
        indexes=[make_index(table="archive.orders", definition="(customer_id)")],
        queries=[make_query(normalized_sql="SELECT * FROM sales.orders WHERE customer_id=?")],
    )
    findings = MissingIndexCandidate().evaluate(snapshot)
    assert len(findings) == 1
    assert findings[0].affected_object == "sales.orders"
    assert 'ON "sales"."orders"' in suggested_sql(findings[0])
    snapshot.queries[0].normalized_sql = "SELECT * FROM orders WHERE customer_id=?"
    assert not MissingIndexCandidate().evaluate(snapshot)


def test_empty_snapshot_has_no_health_claim():
    snapshot = make_snapshot()
    result = run_all(snapshot)
    assert result.score.score is None
    html = render_report(result, snapshot, client_alias="Empty")
    assert "insufficient evidence" in html
    assert "100/100" not in html
    assert "healthy with room" not in html
