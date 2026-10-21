"""Parse MySQL slow query log entries into normalized query statistics."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict

from engine.models import QueryStat
from engine.sql_lexer import redact_sql

_TIME = re.compile(r"^#\s*Query_time:\s*([\d.]+).*?Rows_sent:\s*(\d+).*?Rows_examined:\s*(\d+)", re.M)


def parse_mysql_slow_log(source: str) -> list[QueryStat]:
    """Aggregate standard MySQL slow-log statements after stripping literals."""
    entries = re.split(r"(?m)^# Time: .*\n", source)
    grouped: dict[str, dict[str, float | int | str]] = defaultdict(
        lambda: {"calls": 0, "total": 0.0, "rows_sent": 0, "rows_examined": 0}
    )
    for entry in entries:
        timing = _TIME.search(entry)
        if not timing:
            continue
        sql = re.search(r"(?ms)^\s*((?:SELECT|UPDATE|INSERT|DELETE|REPLACE|WITH|CALL)\b.*?);?\s*$", entry, re.I)
        if not sql:
            continue
        normalized = redact_sql(sql.group(1).strip().rstrip(";"), mysql=True)
        if not normalized:
            continue
        seconds, sent, examined = timing.groups()
        bucket = grouped[normalized]
        bucket["calls"] += 1
        bucket["total"] += float(seconds) * 1000
        bucket["rows_sent"] += int(sent)
        bucket["rows_examined"] += int(examined)

    result = []
    for sql, values in grouped.items():
        calls = int(values["calls"])
        result.append(QueryStat(
            query_digest=hashlib.sha256(sql.encode()).hexdigest()[:32],
            normalized_sql=sql,
            source="slow_query_log",
            calls=calls,
            total_time_ms=float(values["total"]),
            mean_time_ms=float(values["total"]) / calls,
            rows_returned=int(values["rows_sent"]),
            rows_examined=int(values["rows_examined"]),
            full_scan_flag=None,
        ))
    return sorted(result, key=lambda q: q.total_time_ms, reverse=True)[:200]
