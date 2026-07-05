"""T2.3 acceptance: >=12 literal-stripping cases, all green.

Nothing that looks like a literal value may survive normalization — this is
the privacy guarantee the whole product stands on.
"""

import pytest

from collector.pg_collect import digest_of, make_host_alias, normalize_sql

CASES = [
    # (id, input, expected)
    (
        "plain string",
        "SELECT * FROM users WHERE email = 'alice@example.com'",
        "SELECT * FROM users WHERE email = ?",
    ),
    (
        "escaped quote inside string",
        "SELECT 1 FROM t WHERE name = 'O''Brien'",
        "SELECT ? FROM t WHERE name = ?",
    ),
    (
        "backslash-escape string",
        r"SELECT 1 FROM t WHERE bio = E'line1\'s end\n'",
        "SELECT ? FROM t WHERE bio = ?",
    ),
    (
        "dollar-quoted body",
        "SELECT * FROM t WHERE payload = $$secret 'stuff' 42$$",
        "SELECT * FROM t WHERE payload = ?",
    ),
    (
        "tagged dollar quote",
        "SELECT * FROM t WHERE payload = $tag$nested $$ inside$tag$",
        "SELECT * FROM t WHERE payload = ?",
    ),
    (
        "unicode literal",
        "SELECT * FROM users WHERE name = 'Zoë …😀'",
        "SELECT * FROM users WHERE name = ?",
    ),
    (
        "integers and floats",
        "SELECT * FROM orders WHERE total > 199.99 AND qty <= 40",
        "SELECT * FROM orders WHERE total > ? AND qty <= ?",
    ),
    (
        "scientific notation",
        "SELECT * FROM m WHERE v < 1.5e-3",
        "SELECT * FROM m WHERE v < ?",
    ),
    (
        "numbers inside identifiers survive",
        "SELECT col1, col2 FROM tab3 WHERE col1 = 5",
        "SELECT col1, col2 FROM tab3 WHERE col1 = ?",
    ),
    (
        "IN-list collapses",
        "SELECT * FROM t WHERE id IN (1, 2, 3, 4, 5)",
        "SELECT * FROM t WHERE id IN (?)",
    ),
    (
        "IN-list of strings collapses",
        "SELECT * FROM t WHERE status in ('a','b','c')",
        "SELECT * FROM t WHERE status in (?)",
    ),
    (
        "pg parameter markers unified",
        "SELECT * FROM t WHERE a = $1 AND b = $2",
        "SELECT * FROM t WHERE a = ? AND b = ?",
    ),
    (
        "array literal",
        "SELECT * FROM t WHERE tags @> ARRAY['a', 'b']",
        "SELECT * FROM t WHERE tags @> ARRAY[?, ?]",
    ),
    (
        "cast keeps type name",
        "SELECT '2026-01-01'::date, 42::bigint",
        "SELECT ?::date, ?::bigint",
    ),
    (
        "whitespace collapsed",
        "SELECT *\n  FROM t\n WHERE x = 1",
        "SELECT * FROM t WHERE x = ?",
    ),
    (
        "negative number",
        "SELECT * FROM t WHERE balance < -100",
        "SELECT * FROM t WHERE balance < ?",
    ),
]


@pytest.mark.parametrize(("name", "sql", "expected"), CASES, ids=[c[0] for c in CASES])
def test_literal_stripping(name, sql, expected):
    assert normalize_sql(sql) == expected


@pytest.mark.parametrize(
    "sql",
    [c[1] for c in CASES],
    ids=[c[0] for c in CASES],
)
def test_no_pii_fragments_survive(sql):
    out = normalize_sql(sql)
    for fragment in ("alice@example.com", "O'Brien", "secret", "Zoë", "199.99", "2026-01-01"):
        assert fragment not in out


def test_digest_is_stable_across_literal_variants():
    a = digest_of("SELECT * FROM users WHERE email = 'a@x.com'")
    b = digest_of("SELECT * FROM users WHERE email = 'b@y.org'")
    assert a == b
    assert len(a) == 16


def test_host_alias_hashed_by_default():
    alias = make_host_alias("db.internal.corp", "prod", keep_names=False)
    assert "db.internal.corp" not in alias
    assert "prod" not in alias
    assert len(alias) == 12
    assert make_host_alias("db.internal.corp", "prod", keep_names=True) == "db.internal.corp/prod"
