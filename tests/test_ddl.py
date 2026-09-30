from click.testing import CliRunner

from cli.audit import main
from engine.ddl import ingest_ddl
from engine.run import run_all
from report.render import render_report
from tests.rules.conftest import make_snapshot

PG = """CREATE TABLE public.orders(id int PRIMARY KEY, customer_id int);
CREATE INDEX order_customer ON public.orders(customer_id);
CREATE PROCEDURE public.p(IN p_id int) LANGUAGE plpgsql AS $body1$
DECLARE v_count int := 0;
BEGIN
CREATE TEMP TABLE tmp AS SELECT * FROM public.orders WHERE customer_id=p_id;
SELECT count(*) INTO v_count FROM tmp;
CREATE INDEX tmp_id ON tmp (id);
DROP TABLE tmp;
EXECUTE 'SELECT private_token';
END;
$body1$;"""
MY = """DELIMITER $$
CREATE PROCEDURE shop.p(IN p_id INT)
BEGIN
DECLARE v_count INT DEFAULT 0;
CREATE TEMPORARY TABLE tmp (id INT);
INSERT INTO tmp SELECT id FROM shop.orders WHERE id=p_id;
SELECT count(*) INTO v_count FROM tmp;
END$$
DELIMITER ;
CREATE TABLE shop.orders(id INT PRIMARY KEY);"""


def test_postgres_routine_variables_temp_lifecycle_and_redaction():
    catalog = ingest_ddl([PG], "postgres")
    assert not catalog.warnings
    routine = catalog.routines[0]
    assert routine.name == "public.p"
    assert [v.name for v in routine.parameters] == ["p_id"]
    assert [v.name for v in routine.variables] == ["v_count"]
    assert routine.variables[0].assignment_lines == [4, 7]
    assert routine.dependencies == ["public.orders"]
    temp = routine.temporary_tables[0]
    assert temp.name == "tmp"
    assert temp.creation_line == 6
    assert temp.read_lines == [7]
    assert temp.drop_lines == [9]
    assert temp.indexes == ["tmp_id"]
    assert routine.dynamic_sql_lines == [10]
    assert "private_token" not in catalog.model_dump_json()


def test_mysql_delimiters_and_variables():
    catalog = ingest_ddl([MY], "mysql")
    assert not catalog.warnings
    assert catalog.tables[0].name == "shop.orders"
    routine = catalog.routines[0]
    assert routine.name == "shop.p"
    assert routine.dependencies == ["shop.orders"]
    assert routine.temporary_tables[0].columns == ["id"]
    assert routine.temporary_tables[0].write_lines == [5, 6]
    assert routine.variables[0].name == "v_count"


def test_unsupported_sql_and_language_are_visible():
    catalog = ingest_ddl(
        [
            "SET search_path=public; CREATE FUNCTION public.f() RETURNS int "
            "LANGUAGE plpython3u AS $$return 1$$;"
        ],
        "postgres",
    )
    assert catalog.warnings
    assert "unsupported" in catalog.routines[0].limitations[0].lower()


def test_ddl_only_report_and_cli(tmp_path):
    path = tmp_path / "schema.sql"
    path.write_text(PG)
    out = tmp_path / "report"
    result = CliRunner().invoke(
        main,
        ["--ddl", str(path), "--engine", "postgres", "--out", str(out), "--skip-pdf", "--skip-ai"],
    )
    assert result.exit_code == 0, result.output
    assert (out / "schema.json").exists()
    html = (out / "report.html").read_text()
    assert "insufficient evidence" in html
    assert "public.p" in html and "v_count" in html and "Temporary tables" in html
    assert "private_token" not in html


def test_routine_review_is_informational_and_escaped():
    snapshot = make_snapshot(schema_catalog=ingest_ddl([PG], "postgres"))
    result = run_all(snapshot)
    findings = [f for f in result.findings if f.rule_id == "R-SP1"]
    assert findings and all(f.severity == "INFO" for f in findings)
    html = render_report(result, snapshot, client_alias="<script>bad</script>")
    assert "<script>bad</script>" not in html


def test_schema_index_suppresses_missing_index_candidate():
    from engine.rules.index_rules import MissingIndexCandidate
    from tests.rules.conftest import MB, make_query, make_table

    snapshot = make_snapshot(
        schema_catalog=ingest_ddl([PG], "postgres"),
        tables=[make_table(name="orders", size_bytes=200 * MB, seq_scans=1000)],
        queries=[make_query(normalized_sql="SELECT * FROM public.orders WHERE customer_id=?")],
    )
    assert not MissingIndexCandidate().evaluate(snapshot)


def test_constraints_mysql_inline_indexes_and_postgres_alter():
    mysql = ingest_ddl(
        [
            "USE shop; CREATE TABLE t(id INT, x INT, PRIMARY KEY(id), "
            "KEY ix (x), UNIQUE KEY ux (id,x));"
        ],
        "mysql",
    )
    assert mysql.tables[0].name == "shop.t"
    assert {tuple(i.columns) for i in mysql.indexes} == {("id",), ("x",), ("id", "x")}
    assert mysql.tables[0].columns[0].primary_key
    pg = ingest_ddl(
        [
            "CREATE TABLE public.t(id int); "
            "ALTER TABLE ONLY public.t ADD CONSTRAINT t_pk PRIMARY KEY(id);"
        ],
        "postgres",
    )
    assert not pg.warnings
    assert pg.indexes[0].primary
    assert pg.tables[0].columns[0].nullable is False


def test_type_literals_and_defaults_are_not_stored():
    catalog = ingest_ddl(
        ["CREATE TABLE t(x ENUM('private_token') DEFAULT 'private_token');"], "mysql"
    )
    assert "private_token" not in catalog.model_dump_json()


def test_limits_and_malformed_input():
    import pytest

    with pytest.raises(ValueError, match="20 files"):
        ingest_ddl([""] * 21, "postgres")
    with pytest.raises(ValueError, match="Unterminated"):
        ingest_ddl(["CREATE FUNCTION f() AS $x1$private_token"], "postgres")
    with pytest.raises(ValueError, match="supports"):
        ingest_ddl([""], "sqlserver")


def test_multi_schema_and_shadowed_variables_report_limitations():
    sql = """CREATE PROCEDURE public.p(p_id int) LANGUAGE plpgsql AS $$
    DECLARE n int;
    BEGIN
      DECLARE n int;
      BEGIN n := 2; END;
    END; $$;"""
    catalog = ingest_ddl([sql], "postgres")
    assert any("shadowing" in note for note in catalog.routines[0].limitations)
    mysql = ingest_ddl(
        ["USE sales; CREATE TABLE orders(id int);", "USE archive; CREATE TABLE orders(id int);"],
        "mysql",
    )
    assert [t.name for t in mysql.tables] == ["sales.orders", "archive.orders"]
