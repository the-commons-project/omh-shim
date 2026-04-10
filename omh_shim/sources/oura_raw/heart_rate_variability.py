"""Convert an Oura ``/v2/usercollection/daily_readiness/data[i]`` item to
the local ``omh:heart-rate-variability:1.0`` placeholder schema.

Mapping logic designed following dicristea/oura-clinical-workbench conventions
(dicristea's mapping_config does not cover HRV specifically). See AUTHORS.md.

Input shape (from Oura v2 API)::

    {
        "day": "2026-04-09",
        "score": 85,
        "timestamp": "2026-04-09T08:00:00+00:00",
        "contributors": {
            "hrv_balance": 70,
            ...
        }
    }

Note: Oura's ``daily_readiness`` does not expose raw HRV in ms; it exposes a
normalized 0-100 ``hrv_balance`` contributor. To produce a valid
``omh:heart-rate-variability:1.0`` record (which requires a ms value), this
converter prefers a nested ``contributors.hrv_balance_ms`` field if present,
otherwise pulls the top-level ``rmssd`` field from the Oura ``/v2/usercollection/heartrate``
(type=rmssd) alternative endpoint. Callers should pass the shape that has a
real ms value; passing only ``hrv_balance`` (0-100 score) will raise ``KeyError``.
"""

from omh_shim._dispatch import register
from omh_shim.sources._common import isoformat, parse_datetime


@register(source="oura_raw", data_type="heart_rate_variability")
def convert(sample: dict) -> dict:
    # Prefer an explicit ms value. Oura's daily_readiness exposes a normalized
    # "hrv_balance" 0-100 contributor which is not a valid HRV in ms and
    # cannot be safely converted to ms — callers must pass a source with a
    # real ms value (e.g. an enriched contributors dict or the rmssd field).
    if "rmssd" in sample:
        value_ms = sample["rmssd"]
        timestamp = sample.get("timestamp") or sample.get("day")
    elif "contributors" in sample and isinstance(sample["contributors"], dict) and "hrv_balance_ms" in sample["contributors"]:
        value_ms = sample["contributors"]["hrv_balance_ms"]
        timestamp = sample.get("timestamp") or sample.get("day")
    else:
        raise KeyError(
            "oura_raw heart_rate_variability requires either 'rmssd' or "
            "'contributors.hrv_balance_ms' — the normalized 0-100 hrv_balance "
            "score is not a valid HRV measurement in milliseconds"
        )

    if timestamp is None:
        raise KeyError("oura_raw heart_rate_variability requires 'timestamp' or 'day'")

    return {
        "heart_rate_variability": {"value": float(value_ms), "unit": "ms"},
        "effective_time_frame": {"date_time": isoformat(parse_datetime(timestamp))},
    }
