"""T2.17: full-engine golden tests on real testbed snapshots.

fixtures/pg_full.json and fixtures/mysql_full.json were captured from the
docker-compose testbed after full-scale seeding and the mixed problem
workload. These tests freeze WHICH findings fire (rule ids + affected
objects) — not exact numbers, which vary run to run.

If a rule change legitimately alters this set, re-check the diff against
testbed/README.md's planted-problem table before updating expectations.
"""

import json
from pathlib import Path

import pytest

from engine.models import Snapshot
from engine.run import run_all

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _result(name):
    return run_all(Snapshot.model_validate(json.loads((FIXTURES / name).read_text())))


@pytest.fixture(scope="module")
def pg():
    return _result("pg_full.json")


@pytest.fixture(scope="module")
def mysql():
    return _result("mysql_full.json")


def test_pg_expected_rule_set(pg):
    assert sorted(f.rule_id for f in pg.findings) == [
        "R-CFG-PG",  # effective_cache_size at default
        "R-CFG-PG",  # random_page_cost = 4
        "R-I1",  # missing index on orders.customer_id
        "R-I2",  # unused users_email_dup_idx
        "R-I2",  # unused users_email_idx
        "R-I3",  # duplicate email index pair
        "R-Q1",  # planted full-scan query dominates DB time
        "R-Q2",  # testbed lock-holder artifacts (pg_sleep, blocked UPDATE)
        "R-Q2",
        "R-Q3",  # planted N+1 lookup
    ]


def test_pg_planted_problems_map_to_findings(pg):
    by_rule = {}
    for f in pg.findings:
        by_rule.setdefault(f.rule_id, []).append(f)

    # P1: unindexed filter -> R-Q1 (CRITICAL) + R-I1 suggesting customer_id
    assert "customer_id" in by_rule["R-Q1"][0].affected_object
    assert by_rule["R-Q1"][0].severity == "CRITICAL"
    assert by_rule["R-I1"][0].affected_object == "orders"
    assert by_rule["R-I1"][0].evidence["candidate_columns"] == "customer_id"

    # P2: N+1 -> R-Q3 on the order_items lookup, low confidence (single snapshot)
    assert "order_items" in by_rule["R-Q3"][0].affected_object
    assert by_rule["R-Q3"][0].confidence == "low"

    # P5: duplicate index pair -> R-I3 + both email indexes unused (R-I2)
    assert "users_email" in by_rule["R-I3"][0].affected_object
    i2_objects = {f.affected_object for f in by_rule["R-I2"]}
    assert i2_objects == {"public.users.users_email_idx", "public.users.users_email_dup_idx"}


def test_mysql_expected_rule_set(mysql):
    assert sorted(f.rule_id for f in mysql.findings) == [
        "R-CFG-MY",  # innodb_log_file_size at small default
        "R-CFG-MY",  # slow_query_log off
        "R-I1",  # missing index on orders.customer_id
        "R-I2",  # unused users_email_dup_idx (sys.schema_unused_indexes)
        "R-I3",  # redundant email index (sys.schema_redundant_indexes)
        "R-Q1",  # planted full-scan query dominates DB time
        "R-Q2",  # testbed lock-holder artifacts (SLEEP, blocked UPDATE)
        "R-Q2",
    ]


def test_mysql_planted_problems_map_to_findings(mysql):
    by_rule = {}
    for f in mysql.findings:
        by_rule.setdefault(f.rule_id, []).append(f)

    assert "customer_id" in by_rule["R-Q1"][0].affected_object
    assert by_rule["R-I1"][0].affected_object == "orders"
    assert by_rule["R-I1"][0].evidence["candidate_columns"] == "customer_id"
    assert "users_email" in by_rule["R-I3"][0].affected_object
    assert "users_email" in by_rule["R-I2"][0].affected_object


def test_no_primary_key_flagged_unused(pg, mysql):
    for result in (pg, mysql):
        for f in result.findings:
            if f.rule_id == "R-I2":
                assert "pkey" not in f.affected_object.lower()
                assert "PRIMARY" not in f.affected_object


def test_scores_are_sensible(pg, mysql):
    # unhealthy testbed: clearly degraded but nowhere near zeroed
    assert 40 <= pg.score.score <= 90
    assert 40 <= mysql.score.score <= 90
    assert len(pg.score.top_findings) == 5
    assert pg.score.top_findings[0].rule_id == "R-Q1"
