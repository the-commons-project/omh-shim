"""Converters for Open Wearables normalized read-API shapes -> Open mHealth schemas.

Converter signature is uniformly
``(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]``.
``tz`` is only consulted by daily (``date``-keyed) converters.
"""

from collections.abc import Mapping
from datetime import timedelta, tzinfo
from typing import Any

from omh_shim._helpers import (
    date_time_frame,
    day_interval,
    interval_from_bounds,
    isoformat,
    parse_datetime,
    set_optional,
    unit_value,
)
from omh_shim.errors import ConversionError


def heart_rate(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """OW ``TimeSeriesSample`` (type=heart_rate) -> ``omh:heart-rate:2.0``.

    Input::

        {"timestamp": "2026-04-09T08:30:00+00:00", "type": "heart_rate",
         "value": 72, "unit": "bpm", "source": {...}}
    """
    return {
        "heart_rate": unit_value(sample["value"], "beats/min"),
        "effective_time_frame": date_time_frame(sample["timestamp"]),
    }


def heart_rate_variability(
    sample: Mapping[str, Any], *, tz: tzinfo | None
) -> dict[str, Any]:
    """OW ``TimeSeriesSample`` (type=heart_rate_variability) -> ``local:heart-rate-variability:1.0``."""
    return {
        "heart_rate_variability": unit_value(sample["value"], "ms"),
        "effective_time_frame": date_time_frame(sample["timestamp"]),
    }


def step_count(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """OW step-count input -> ``omh:step-count:3.0``.

    Two supported input shapes:

    1. ``ActivitySummary``: ``{"date": "2026-04-09", "steps": 8432, ...}``
       — ``effective_time_frame`` covers the full day in ``tz``.
    2. ``TimeSeriesSample`` with ``type=steps``: ``{"timestamp": ..., "value": 12, ...}``
       — OMH rejects ``date_time`` for this schema, so the converter builds a
       1-minute interval ending at ``timestamp`` (OW's per-minute resolution).
    """
    if "date" in sample:
        steps = sample["steps"]
        time_interval = day_interval(sample["date"], tz=tz)
    elif "timestamp" in sample and sample.get("type") == "steps":
        steps = sample["value"]
        end = parse_datetime(sample["timestamp"])
        start = end - timedelta(minutes=1)
        time_interval = {"start_date_time": isoformat(start), "end_date_time": isoformat(end)}
    else:
        raise ConversionError(
            "ow_normalized step_count input must have either {'date', 'steps'} "
            "(ActivitySummary) or {'timestamp', 'type': 'steps', 'value'} "
            "(TimeSeriesSample) keys"
        )
    return {
        "step_count": unit_value(steps, "steps", cast=int),
        "effective_time_frame": {"time_interval": time_interval},
    }


def sleep_duration(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """OW ``ActivitySummary`` (sleep fields) -> ``omh:sleep-duration:2.0``.

    OMH requires a ``time_interval`` — uses the caller-provided ``tz`` for day bounds.
    """
    return {
        "sleep_duration": unit_value(
            sample["sleep_total_duration_minutes"] * 60, "sec", cast=int
        ),
        "effective_time_frame": {"time_interval": day_interval(sample["date"], tz=tz)},
    }


def sleep_episode(sample: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """OW sleep details -> ``omh:sleep-episode:1.1``.

    Only ``effective_time_frame`` is schema-required. OMH sleep-episode:1.1
    does not carry per-stage breakdowns; downstream consumers wanting stages
    should look at sleep-stage-summary schemas (not in v0.1 scope).
    """
    out: dict[str, Any] = {
        "effective_time_frame": {
            "time_interval": interval_from_bounds(sample["bedtime_start"], sample["bedtime_end"])
        }
    }
    set_optional(
        out, "total_sleep_time", sample, "sleep_total_duration_minutes",
        unit="sec", cast=int, scale=60,
    )
    set_optional(
        out, "wake_after_sleep_onset", sample, "sleep_awake_minutes",
        unit="sec", cast=int, scale=60,
    )
    set_optional(
        out, "sleep_maintenance_efficiency_percentage", sample,
        "sleep_efficiency_score", unit="%",
    )
    if (is_nap := sample.get("is_nap")) is not None:
        out["is_main_sleep"] = not is_nap
    return out


def physical_activity(
    sample: Mapping[str, Any], *, tz: tzinfo | None
) -> dict[str, Any]:
    """OW ``ActivitySummary`` -> ``omh:physical-activity:1.2``.

    Only ``activity_name`` is schema-required. Step counts go through the
    dedicated ``step_count`` converter; active minutes are not modeled here.
    """
    out: dict[str, Any] = {
        "activity_name": "daily activity summary",
        "effective_time_frame": {"time_interval": day_interval(sample["date"], tz=tz)},
    }
    set_optional(out, "distance", sample, "distance_meters", unit="m")
    set_optional(out, "kcal_burned", sample, "active_calories_kcal", unit="kcal")
    return out
