"""Shared helpers for source converters.

Most of what's in here is small enough that inlining it would be fine, but
factoring keeps converter modules focused on field mapping rather than on
date math and dict-shape boilerplate.
"""

from datetime import datetime, timedelta, timezone
from typing import Any


def parse_datetime(value: Any) -> datetime:
    """Parse an ISO-8601 datetime string. Naive results are coerced to UTC."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        raise ValueError(f"expected ISO-8601 datetime string, got {type(value).__name__}")
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def isoformat(dt: datetime) -> str:
    """ISO-8601 with ``Z`` suffix when the offset is UTC."""
    return dt.isoformat().replace("+00:00", "Z")


def day_interval(date_str: str) -> dict:
    """Build an OMH ``time_interval`` covering one calendar day in UTC.

    ``date_str`` is a YYYY-MM-DD date. Returns a dict with ``start_date_time``
    and ``end_date_time`` shaped per the OMH time-interval schema's third
    ``oneOf`` branch.
    """
    start = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return {
        "start_date_time": isoformat(start),
        "end_date_time": isoformat(end),
    }


def time_interval_from_bounds(start: str, end: str) -> dict:
    """Build an OMH ``time_interval`` from explicit start/end ISO-8601 strings."""
    return {
        "start_date_time": isoformat(parse_datetime(start)),
        "end_date_time": isoformat(parse_datetime(end)),
    }
