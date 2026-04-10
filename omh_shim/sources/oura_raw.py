"""Converters for raw Oura v2 API response items -> Open mHealth schemas.

Mapping logic ported with permission from
https://github.com/dicristea/oura-clinical-workbench/tree/main/data_syn .
See AUTHORS.md.

Converter signature is uniformly
``(sample: dict[str, Any], *, tz: tzinfo | None) -> dict[str, Any]``.
``tz`` is only consulted by daily (``day``-keyed) converters; timestamp-based
converters ignore it.
"""

from datetime import tzinfo
from typing import Any

from omh_shim._helpers import (
    date_time_frame,
    day_interval,
    interval_from_bounds,
    set_opt,
    uv,
)
from omh_shim.errors import ConversionError


def heart_rate(sample: dict[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """``/v2/usercollection/heartrate/data[i]`` -> ``omh:heart-rate:2.0``.

    Input::

        {"bpm": 72, "source": "sleep", "timestamp": "2026-04-09T03:15:00+00:00"}

    Oura's ``source`` string is context (sleep/awake/rest), not device — OW
    carries it under its own ``source`` metadata when ingesting, so we drop it.
    """
    return {
        "heart_rate": uv(sample["bpm"], "beats/min"),
        "effective_time_frame": date_time_frame(sample["timestamp"]),
    }


def heart_rate_variability(sample: dict[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Oura HRV -> ``local:heart-rate-variability:1.0``.

    Oura's ``daily_readiness`` exposes only a normalized 0-100 ``hrv_balance``
    score, which is NOT a valid HRV in milliseconds. The converter accepts
    either a top-level ``rmssd`` (from the alternative heartrate rmssd feed)
    or a ``contributors.hrv_balance_ms`` field explicitly provided in ms.
    Passing only the 0-100 score raises ``ConversionError``.
    """
    if "rmssd" in sample:
        value_ms = sample["rmssd"]
    elif isinstance(sample.get("contributors"), dict) and "hrv_balance_ms" in sample["contributors"]:
        value_ms = sample["contributors"]["hrv_balance_ms"]
    else:
        raise ConversionError(
            "oura_raw heart_rate_variability requires either 'rmssd' or "
            "'contributors.hrv_balance_ms' — the normalized 0-100 hrv_balance "
            "score is not a valid HRV measurement in milliseconds"
        )

    timestamp = sample.get("timestamp") or sample.get("day")
    if timestamp is None:
        raise ConversionError(
            "oura_raw heart_rate_variability requires 'timestamp' or 'day'"
        )

    return {
        "heart_rate_variability": uv(value_ms, "ms"),
        "effective_time_frame": date_time_frame(timestamp),
    }


def step_count(sample: dict[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """``/v2/usercollection/daily_activity/data[i]`` -> ``omh:step-count:3.0``.

    OMH's step-count:3.0 requires ``effective_time_frame.time_interval``, so
    the converter uses the day's midnight bounds in the caller-provided ``tz``.
    """
    return {
        "step_count": uv(sample["steps"], "steps", cast=int),
        "effective_time_frame": {"time_interval": day_interval(sample["day"], tz=tz)},
    }


def sleep_duration(sample: dict[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Oura sleep/data[i] -> ``omh:sleep-duration:2.0``. Oura already reports
    ``total_sleep_duration`` in seconds — no unit conversion."""
    return {
        "sleep_duration": uv(sample["total_sleep_duration"], "sec", cast=int),
        "effective_time_frame": {
            "time_interval": interval_from_bounds(sample["bedtime_start"], sample["bedtime_end"])
        },
    }


def sleep_episode(sample: dict[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Oura sleep/data[i] -> ``omh:sleep-episode:1.1``.

    Only ``effective_time_frame`` is required. Every optional field that maps
    1:1 from Oura is populated when present. Oura's ``long_sleep``/``short_sleep``
    are both main sleep; only ``nap`` is not.
    """
    out: dict[str, Any] = {
        "effective_time_frame": {
            "time_interval": interval_from_bounds(sample["bedtime_start"], sample["bedtime_end"])
        }
    }
    set_opt(out, "total_sleep_time", sample, "total_sleep_duration", unit="sec", cast=int)
    set_opt(out, "wake_after_sleep_onset", sample, "awake_time", unit="sec", cast=int)
    set_opt(out, "latency_to_sleep_onset", sample, "latency", unit="sec", cast=int)
    set_opt(out, "sleep_maintenance_efficiency_percentage", sample, "efficiency", unit="%")
    if (sleep_type := sample.get("type")) is not None:
        out["is_main_sleep"] = sleep_type != "nap"
    return out


def physical_activity(sample: dict[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    """Oura daily_activity/data[i] -> ``omh:physical-activity:1.2``.

    Only ``activity_name`` is schema-required. ``distance`` comes from
    ``equivalent_walking_distance``; ``kcal_burned`` from ``active_calories``.
    """
    out: dict[str, Any] = {
        "activity_name": "daily activity summary",
        "effective_time_frame": {"time_interval": day_interval(sample["day"], tz=tz)},
    }
    set_opt(out, "distance", sample, "equivalent_walking_distance", unit="m")
    set_opt(out, "kcal_burned", sample, "active_calories", unit="kcal")
    return out
