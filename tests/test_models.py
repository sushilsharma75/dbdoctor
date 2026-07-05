import json
from pathlib import Path

from engine.models import Snapshot, export_json_schema

FIXTURE = Path(__file__).parent.parent / "fixtures" / "minimal_snapshot.json"


def test_fixture_round_trip():
    raw = json.loads(FIXTURE.read_text())
    snap = Snapshot.model_validate(raw)

    assert snap.meta.engine == "postgres"
    assert snap.queries[0].calls == 4133
    assert snap.queries[0].rows_examined is None  # PG has no rows_examined
    assert snap.queries[1].full_scan_flag is False  # MySQL-shaped entry
    assert snap.tables[0].schema_name == "public"
    assert snap.indexes[0].is_duplicate_candidate is True
    assert snap.connections.max_limit == 100

    # serialize -> reparse -> identical model
    reparsed = Snapshot.model_validate_json(snap.model_dump_json())
    assert reparsed == snap


def test_json_schema_exports():
    schema = export_json_schema()
    assert schema["title"] == "Snapshot"
    defs = schema["$defs"]
    for model in (
        "SnapshotMeta",
        "QueryStat",
        "TableStat",
        "IndexStat",
        "SessionInfo",
        "LockWait",
        "ConnectionInfo",
        "ConfigSetting",
    ):
        assert model in defs
    # the schema is itself valid JSON
    json.dumps(schema)


def test_every_field_documents_both_engine_sources():
    """T2.1 acceptance: every field docstring names both engine sources."""
    from engine import models

    for model in (
        models.SnapshotMeta,
        models.QueryStat,
        models.TableStat,
        models.IndexStat,
        models.SessionInfo,
        models.LockWait,
        models.ConnectionInfo,
        models.ConfigSetting,
        models.Snapshot,
    ):
        for name, field in model.model_fields.items():
            desc = field.description or ""
            assert "PG" in desc or "Both engines" in desc, f"{model.__name__}.{name}"
            assert "MySQL" in desc or "Both engines" in desc, f"{model.__name__}.{name}"
