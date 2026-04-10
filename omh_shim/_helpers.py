"""Shared helpers for source converters.

Small building blocks used by every converter: datetime parsing/formatting,
time-interval construction, and the ``{"value": x, "unit": "..."}`` dict
shape that OMH uses for every quantitative field.
"""

from datetime import datetime, timedelta, tzinfo
from typing import Any

from omh_shim.errors import ConversionError


def parse_datetime(value: Any) -> datetime:
    """Parse an ISO-8601 datetime string into a timezone-aware datetime.

    Raises ``ConversionError`` for naive datetimes (no tzinfo). Silent UTC
    coercion is a data-quality footgun — a Tokyo user's "22:30" without an
    offset must not be recorded as UTC. Callers must provide explicit
    timezone offsets in their input data.
    """
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        s = value.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError as e:
            raise ConversionError(f"invalid ISO-8601 datetime: {value!r}") from e
    else:
        raise ConversionError(
            f"expected ISO-8601 datetime string, got {type(value).__name__}"
        )
    if dt.tzinfo is None:
        raise ConversionError(
            f"datetime {value!r} has no timezone; omh-shim requires explicit "
            "timezone offsets to avoid silently misaligning clinical data"
        )
    return dt


def isoformat(dt: datetime) -> str:
    """ISO-8601 with ``Z`` suffix when the offset is UTC."""
    return dt.isoformat().replace("+00:00", "Z")


def day_interval(date_str: str, tz: tzinfo | None) -> dict:
    """OMH ``time_interval`` covering one calendar day in the given timezone.

    ``tz`` is REQUIRED (pass ``datetime.UTC`` explicitly when you mean UTC).
    A "day" in Tokyo is not a "day" in UTC; silently defaulting to UTC
    would misalign daily summaries by up to 24 hours for any non-UTC user.
    """
    if tz is None:
        raise ConversionError(
            "this data type aggregates over a calendar day and requires an "
            "explicit timezone — pass tz=... to convert() so the day boundaries "
            "reflect the user's local calendar day, not UTC"
        )
    start = datetime.fromisoformat(date_str).replace(tzinfo=tz)
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
    scale: float = 1,
) -> None:
    """Set ``out[out_key]`` to a unit_value if ``sample[field]`` is not None/missing.

    ``scale`` is applied after ``cast`` (e.g. minutes -> seconds uses scale=60).
    """
    v = sample.get(field)
    if v is None:
        return
    out[out_key] = {"value": cast(v) * scale, "unit": unit}
