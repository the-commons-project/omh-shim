"""Shared helpers for source converters.

Small building blocks used by every converter: datetime parsing/formatting,
OMH time-interval construction, and the ``{"value": x, "unit": "..."}`` dict
shape that OMH uses for every quantitative field.
"""

from datetime import UTC, datetime, timedelta
from typing import Any


def parse_datetime(value: Any) -> datetime:
    """Parse an ISO-8601 datetime string. Naive results are coerced to UTC."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str):
        raise ValueError(f"expected ISO-8601 datetime string, got {type(value).__name__}")
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def isoformat(dt: datetime) -> str:
    """ISO-8601 with ``Z`` suffix when the offset is UTC."""
    return dt.isoformat().replace("+00:00", "Z")


def day_interval(date_str: str) -> dict:
    """OMH ``time_interval`` covering one calendar day in UTC."""
    start = datetime.fromisoformat(date_str).replace(tzinfo=UTC)
    end = start + timedelta(days=1)
    return {"start_date_time": isoformat(start), "end_date_time": isoformat(end)}


def interval_from_bounds(start: str, end: str) -> dict:
    """OMH ``time_interval`` from explicit start/end ISO-8601 strings."""
    return {
        "start_date_time": isoformat(parse_datetime(start)),
        "end_date_time": isoformat(parse_datetime(end)),
    }


def date_time_frame(timestamp: Any) -> dict:
    """OMH ``effective_time_frame`` with a single ``date_time``."""
    return {"date_time": isoformat(parse_datetime(timestamp))}


def uv(value: Any, unit: str, cast=float) -> dict:
    """OMH unit_value dict: ``{"value": cast(value), "unit": unit}``."""
    return {"value": cast(value), "unit": unit}


def set_opt(
    out: dict,
    out_key: str,
    sample: dict,
    field: str,
    *,
    unit: str,
    cast=float,
    scale: int | float = 1,
) -> None:
    """Set ``out[out_key]`` to a unit_value if ``sample[field]`` is not None/missing.

    ``scale`` is applied after ``cast`` (e.g. minutes -> seconds uses scale=60).
    """
    v = sample.get(field)
    if v is None:
        return
    out[out_key] = {"value": cast(v) * scale, "unit": unit}
