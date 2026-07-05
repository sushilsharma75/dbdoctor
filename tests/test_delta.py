"""T2.5 acceptance: extrapolation math verified; resets flagged, not miscalculated."""

import copy

import pytest

from collector.delta import apply_delta


def _snap(collected_at: str, calls: int, total_ms: float, table_size: int) -> dict:
    return {
        "meta": {"collected_at": collected_at, "is_delta": False, "delta_interval_seconds": None},
        "queries": [
            {
                "query_digest": "q1",
                "calls": calls,
                "total_time_ms": total_ms,
                "calls_per_day": None,
                "time_per_day_ms": None,
                "delta_low_confidence": None,
            }
        ],
        "tables": [
            {
                "schema_name": "public",
                "name": "orders",
                "size_bytes": table_size,
                "growth_30d_pct": None,
            }
        ],
    }


def test_normal_diff_and_interval_extrapolation():
    prev = _snap("2026-07-01T00:00:00+00:00", calls=1000, total_ms=5000.0, table_size=1_000_000)
    cur = _snap("2026-07-03T00:00:00+00:00", calls=3000, total_ms=9000.0, table_size=1_100_000)

    out = apply_delta(cur, prev)

    q = out["queries"][0]
    assert q["calls_per_day"] == 1000.0  # 2000 calls over 2 days
    assert q["time_per_day_ms"] == 2000.0  # 4000 ms over 2 days
    assert q["delta_low_confidence"] is False
    # 10% growth over 2 days -> 150% per 30 days
    assert out["tables"][0]["growth_30d_pct"] == 150.0
    assert out["meta"]["is_delta"] is True
    assert out["meta"]["delta_interval_seconds"] == 2 * 86400


def test_counter_reset_flagged_not_miscalculated():
    prev = _snap("2026-07-01T00:00:00+00:00", calls=50_000, total_ms=90_000.0, table_size=100)
    cur = _snap("2026-07-02T00:00:00+00:00", calls=200, total_ms=400.0, table_size=100)

    q = apply_delta(cur, prev)["queries"][0]

    assert q["delta_low_confidence"] is True
    assert q["calls_per_day"] == 200.0  # from post-reset counters, never negative
    assert q["calls_per_day"] >= 0


def test_new_query_and_new_table():
    prev = _snap("2026-07-01T00:00:00+00:00", calls=10, total_ms=10.0, table_size=500)
    cur = _snap("2026-07-02T00:00:00+00:00", calls=20, total_ms=20.0, table_size=600)
    cur["queries"].append(
        {
            "query_digest": "brand_new",
            "calls": 480,
            "total_time_ms": 960.0,
            "calls_per_day": None,
            "time_per_day_ms": None,
            "delta_low_confidence": None,
        }
    )
    cur["tables"].append(
        {
            "schema_name": "public",
            "name": "brand_new_table",
            "size_bytes": 42,
            "growth_30d_pct": None,
        }
    )

    out = apply_delta(cur, prev)

    new_q = out["queries"][1]
    assert new_q["delta_low_confidence"] is True
    assert new_q["calls_per_day"] == 480.0
    # a table with no baseline gets no growth claim at all
    assert out["tables"][1]["growth_30d_pct"] is None


def test_wrong_order_rejected():
    prev = _snap("2026-07-02T00:00:00+00:00", 1, 1.0, 1)
    cur = _snap("2026-07-01T00:00:00+00:00", 2, 2.0, 1)
    with pytest.raises(ValueError, match="older"):
        apply_delta(copy.deepcopy(cur), prev)
