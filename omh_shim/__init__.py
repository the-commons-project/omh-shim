"""omh-shim: convert wearable health data to Open mHealth schemas.

Single-file, zero-dependency library. Converts Oura Ring v2 and Open Wearables
normalized samples to IEEE 1752.1 data-point envelopes conforming to Open
mHealth schemas.

Usage::

    from datetime import UTC
    from omh_shim import to_omh

    result = to_omh(
        "oura_raw", "heart_rate",
        {"bpm": 72, "timestamp": "2026-04-09T08:00:00Z"},
    )
    # -> {"header": {...}, "body": {...}}

``tz`` is required for daily data types (step_count, physical_activity,
sleep_duration). Raises ``ConvertError`` on invalid input.
"""

import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta, tzinfo
from types import MappingProxyType
from typing import Any

__all__ = [
    "to_omh",
    "convert",  # deprecated alias for to_omh
    "ConvertError",
    "ConversionError",
    "ValidationError",
    "SCHEMA_IDS",
]
__version__ = "0.2.0"


class ConvertError(Exception):
    """Base class for all omh-shim errors.
    Catch ``ConvertError`` to handle both conversion and validation failures."""


class ConversionError(ConvertError):
    """Raised when a sample cannot be converted to a valid OMH data point
    (bad input shape, missing required fields, naive datetimes, etc.)."""


class ValidationError(ConvertError):
    """Raised when converter output does not conform to its target OMH schema.
    Only raised when ``to_omh(..., validate=True)`` and ``jsonschema`` is
    installed (via ``pip install omh-shim[validate]``)."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_dt(value: Any) -> datetime:
    """Parse ISO-8601 into a tz-aware datetime. Rejects naive datetimes —
    silent UTC coercion is a clinical-data footgun."""
    if not isinstance(value, str):
        raise ConversionError(f"expected ISO-8601 string, got {type(value).__name__}")
    try:
        dt = datetime.fromisoformat(value.strip())
    except ValueError as e:
        raise ConversionError(f"invalid ISO-8601 datetime: {value!r}") from e
    if dt.tzinfo is None:
        raise ConversionError(
            f"datetime {value!r} has no timezone; omh-shim requires explicit "
            "timezone offsets to avoid silently misaligning clinical data"
        )
    return dt


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _uv(value: Any, unit: str, cast: Callable[[Any], Any] = float) -> dict[str, Any]:
    return {"value": cast(value), "unit": unit}


def _time_frame(ts: Any) -> dict[str, Any]:
    return {"date_time": _iso(_parse_dt(ts))}


def _day_interval(date_str: str, *, tz: tzinfo | None) -> dict[str, Any]:
    if tz is None:
        raise ConversionError(
            "this data type requires an explicit timezone — pass tz=... to "
            "to_omh() so day boundaries reflect the user's local calendar day"
        )
    if "T" in date_str:
        raise ConversionError(f"expected YYYY-MM-DD date, got datetime: {date_str!r}")
    try:
        start = datetime.fromisoformat(date_str).replace(tzinfo=tz)
    except ValueError as e:
        raise ConversionError(f"invalid YYYY-MM-DD date: {date_str!r}") from e
    end = start + timedelta(days=1)
    return {"start_date_time": _iso(start), "end_date_time": _iso(end)}


def _bounds(start: str, end: str) -> dict[str, Any]:
    return {"start_date_time": _iso(_parse_dt(start)), "end_date_time": _iso(_parse_dt(end))}


def _set_opt(
    out: dict[str, Any],
    key: str,
    sample: Mapping[str, Any],
    field: str,
    *,
    unit: str,
    cast: Callable[[Any], Any] = float,
    scale: float = 1,
) -> None:
    v = sample.get(field)
    if v is not None:
        out[key] = _uv(v * scale, unit, cast)


# ---------------------------------------------------------------------------
# Converters — oura_raw
# ---------------------------------------------------------------------------


def _oura_heart_rate(s: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    return {
        "heart_rate": _uv(s["bpm"], "beats/min"),
        "effective_time_frame": _time_frame(s["timestamp"]),
    }


def _oura_heart_rate_variability(s: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    if "rmssd" in s:
        ms = s["rmssd"]
    elif isinstance(s.get("contributors"), dict) and "hrv_balance_ms" in s["contributors"]:
        ms = s["contributors"]["hrv_balance_ms"]
    else:
        raise ConversionError(
            "oura_raw heart_rate_variability requires either 'rmssd' or "
            "'contributors.hrv_balance_ms' — the normalized 0-100 hrv_balance "
            "score is not a valid HRV measurement in milliseconds"
        )
    ts = s.get("timestamp") or s.get("day")
    if ts is None:
        raise ConversionError("oura_raw heart_rate_variability requires 'timestamp' or 'day'")
    return {"heart_rate_variability": _uv(ms, "ms"), "effective_time_frame": _time_frame(ts)}


def _oura_step_count(s: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    return {
        "step_count": _uv(s["steps"], "steps", cast=int),
        "effective_time_frame": {"time_interval": _day_interval(s["day"], tz=tz)},
    }


def _oura_sleep_duration(s: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    return {
        "sleep_duration": _uv(s["total_sleep_duration"], "sec", cast=int),
        "effective_time_frame": {"time_interval": _bounds(s["bedtime_start"], s["bedtime_end"])},
    }


def _oura_sleep_episode(s: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "effective_time_frame": {"time_interval": _bounds(s["bedtime_start"], s["bedtime_end"])}
    }
    _set_opt(out, "total_sleep_time", s, "total_sleep_duration", unit="sec", cast=int)
    _set_opt(out, "wake_after_sleep_onset", s, "awake_time", unit="sec", cast=int)
    _set_opt(out, "latency_to_sleep_onset", s, "latency", unit="sec", cast=int)
    _set_opt(out, "sleep_maintenance_efficiency_percentage", s, "efficiency", unit="%")
    if (t := s.get("type")) is not None:
        out["is_main_sleep"] = t != "nap"
    return out


def _oura_physical_activity(s: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "activity_name": "daily activity summary",
        "effective_time_frame": {"time_interval": _day_interval(s["day"], tz=tz)},
    }
    _set_opt(out, "distance", s, "equivalent_walking_distance", unit="m")
    _set_opt(out, "kcal_burned", s, "active_calories", unit="kcal")
    return out


# ---------------------------------------------------------------------------
# Converters — ow_normalized
# ---------------------------------------------------------------------------


def _ow_heart_rate(s: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    return {
        "heart_rate": _uv(s["value"], "beats/min"),
        "effective_time_frame": _time_frame(s["timestamp"]),
    }


def _ow_heart_rate_variability(s: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    return {
        "heart_rate_variability": _uv(s["value"], "ms"),
        "effective_time_frame": _time_frame(s["timestamp"]),
    }


def _ow_step_count(s: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    if "date" in s:
        steps, ti = s["steps"], _day_interval(s["date"], tz=tz)
    elif "timestamp" in s and s.get("type") == "steps":
        steps = s["value"]
        end = _parse_dt(s["timestamp"])
        ti = {"start_date_time": _iso(end - timedelta(minutes=1)), "end_date_time": _iso(end)}
    else:
        raise ConversionError(
            "ow_normalized step_count input must have either {'date', 'steps'} "
            "or {'timestamp', 'type': 'steps', 'value'}"
        )
    return {
        "step_count": _uv(steps, "steps", cast=int),
        "effective_time_frame": {"time_interval": ti},
    }


def _ow_sleep_duration(s: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    return {
        "sleep_duration": _uv(s["sleep_total_duration_minutes"] * 60, "sec", cast=int),
        "effective_time_frame": {"time_interval": _day_interval(s["date"], tz=tz)},
    }


def _ow_sleep_episode(s: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "effective_time_frame": {"time_interval": _bounds(s["bedtime_start"], s["bedtime_end"])}
    }
    _set_opt(
        out,
        "total_sleep_time",
        s,
        "sleep_total_duration_minutes",
        unit="sec",
        cast=int,
        scale=60,
    )
    _set_opt(
        out,
        "wake_after_sleep_onset",
        s,
        "sleep_awake_minutes",
        unit="sec",
        cast=int,
        scale=60,
    )
    _set_opt(out, "sleep_maintenance_efficiency_percentage", s, "sleep_efficiency_score", unit="%")
    if (is_nap := s.get("is_nap")) is not None:
        out["is_main_sleep"] = not is_nap
    return out


def _ow_physical_activity(s: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "activity_name": "daily activity summary",
        "effective_time_frame": {"time_interval": _day_interval(s["date"], tz=tz)},
    }
    _set_opt(out, "distance", s, "distance_meters", unit="m")
    _set_opt(out, "kcal_burned", s, "active_calories_kcal", unit="kcal")
    return out


def _ow_oxygen_saturation(s: Mapping[str, Any], *, tz: tzinfo | None) -> dict[str, Any]:
    return {
        "oxygen_saturation": _uv(s["value"], "%"),
        "effective_time_frame": _time_frame(s["timestamp"]),
    }


# ---------------------------------------------------------------------------
# Registry and public API
# ---------------------------------------------------------------------------

SCHEMA_IDS: Mapping[str, str] = MappingProxyType(
    {
        "heart_rate": "omh:heart-rate:2.0",
        "heart_rate_variability": "local:heart-rate-variability:1.0",
        "step_count": "omh:step-count:3.0",
        "sleep_duration": "omh:sleep-duration:2.0",
        "sleep_episode": "omh:sleep-episode:1.1",
        "physical_activity": "omh:physical-activity:1.2",
        "oxygen_saturation": "omh:oxygen-saturation:2.0",
    }
)
"""Read-only mapping of ``data_type -> schema id``. ``heart_rate_variability``
uses a ``local:`` namespace — Open mHealth has no canonical HRV schema."""

_REGISTRY: dict[tuple[str, str], Callable[..., dict[str, Any]]] = {
    ("oura_raw", "heart_rate"): _oura_heart_rate,
    ("oura_raw", "heart_rate_variability"): _oura_heart_rate_variability,
    ("oura_raw", "step_count"): _oura_step_count,
    ("oura_raw", "sleep_duration"): _oura_sleep_duration,
    ("oura_raw", "sleep_episode"): _oura_sleep_episode,
    ("oura_raw", "physical_activity"): _oura_physical_activity,
    ("ow_normalized", "heart_rate"): _ow_heart_rate,
    ("ow_normalized", "heart_rate_variability"): _ow_heart_rate_variability,
    ("ow_normalized", "step_count"): _ow_step_count,
    ("ow_normalized", "sleep_duration"): _ow_sleep_duration,
    ("ow_normalized", "sleep_episode"): _ow_sleep_episode,
    ("ow_normalized", "physical_activity"): _ow_physical_activity,
    ("ow_normalized", "oxygen_saturation"): _ow_oxygen_saturation,
}


def _header(schema_id: str, *, datasheets: list[dict[str, str]] | None = None) -> dict[str, Any]:
    ns, name, ver = schema_id.split(":", 2)
    h: dict[str, Any] = {
        "uuid": str(uuid.uuid4()),
        "schema_id": {"namespace": ns, "name": name, "version": ver},
        "source_creation_date_time": _iso(datetime.now(UTC)),
        "modality": "sensed",
    }
    if datasheets:
        h["external_datasheets"] = datasheets
    return h


def _datasheets(sample: Mapping[str, Any]) -> list[dict[str, str]] | None:
    """Extract manufacturer reference from sample's source metadata.
    Accepts Oura-shaped (device/provider) or OW-shaped (device_model/source_name) keys."""
    src = sample.get("source")
    if not isinstance(src, Mapping):
        return None
    ref = (
        src.get("device")
        or src.get("device_model")
        or src.get("provider")
        or src.get("source_name")
    )
    return [{"datasheet_type": "manufacturer", "datasheet_reference": str(ref)}] if ref else None


def to_omh(
    source: str,
    data_type: str,
    sample: Mapping[str, Any],
    *,
    tz: tzinfo | None = None,
    validate: bool = False,
) -> dict[str, Any]:
    """Convert one source sample to one Open mHealth data-point envelope.

    Returns ``{"header": {...}, "body": {...}}`` (IEEE 1752.1).

    ``tz`` is required for daily data types (step_count, physical_activity,
    sleep_duration).

    ``validate=True`` runs the output through jsonschema against the target
    OMH schema and raises ``ValidationError`` on mismatch. This requires the
    optional ``jsonschema`` dependency — install with
    ``pip install omh-shim[validate]``. If ``validate=True`` and jsonschema
    is not installed, ``ImportError`` is raised with an install hint.

    Raises ``ConversionError`` on invalid input, ``ValidationError`` on
    schema mismatch (only when ``validate=True``).
    """
    converter = _REGISTRY.get((source, data_type))
    if converter is None:
        raise ConversionError(f"No converter for source={source!r} data_type={data_type!r}")
    try:
        body = converter(sample, tz=tz)
    except (KeyError, ValueError, TypeError) as e:
        raise ConversionError(f"{source}/{data_type}: {type(e).__name__}: {e}") from e
    schema_id = SCHEMA_IDS[data_type]
    if validate:
        _validate_output(body, schema_id)
    return {
        "header": _header(schema_id, datasheets=_datasheets(sample)),
        "body": body,
    }


def _validate_output(body: dict[str, Any], schema_id: str) -> None:
    """Validate ``body`` against ``schema_id`` using jsonschema (optional dep)."""
    try:
        import importlib.resources
        import json

        from jsonschema import Draft7Validator
        from referencing import Registry, Resource
        from referencing.jsonschema import DRAFT7
    except ImportError as e:
        raise ImportError(
            "Runtime schema validation requires the 'jsonschema' extra. "
            "Install with: pip install omh-shim[validate]"
        ) from e

    filenames = {
        "omh:heart-rate:2.0": "omh_heart-rate_2-0.json",
        "local:heart-rate-variability:1.0": "local_heart-rate-variability_1-0.json",
        "omh:step-count:3.0": "omh_step-count_3-0.json",
        "omh:sleep-duration:2.0": "omh_sleep-duration_2-0.json",
        "omh:sleep-episode:1.1": "omh_sleep-episode_1-1.json",
        "omh:physical-activity:1.2": "omh_physical-activity_1-2.json",
        "omh:oxygen-saturation:2.0": "omh_oxygen-saturation_2-0.json",
    }
    schemas_pkg = importlib.resources.files("omh_shim.schemas")
    resources = []
    for entry in schemas_pkg.iterdir():
        if entry.name.endswith(".json"):
            with entry.open("r", encoding="utf-8") as f:
                resources.append(
                    (entry.name, Resource.from_contents(json.load(f), default_specification=DRAFT7))
                )
    with schemas_pkg.joinpath(filenames[schema_id]).open("r", encoding="utf-8") as f:
        validator = Draft7Validator(json.load(f), registry=Registry().with_resources(resources))
    errors = sorted(validator.iter_errors(body), key=lambda e: list(e.absolute_path))
    if errors:
        pieces = [
            f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors
        ]
        raise ValidationError(f"Output does not conform to {schema_id}: " + "; ".join(pieces))


# Deprecated alias for backward compatibility with omh-shim 0.1.x.
# Will be removed in a future major version (see CHANGELOG).
convert = to_omh
