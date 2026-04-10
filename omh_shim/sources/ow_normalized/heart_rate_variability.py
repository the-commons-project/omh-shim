"""Convert an OW ``TimeSeriesSample`` (type=heart_rate_variability) to the
local ``omh:heart-rate-variability:1.0`` placeholder schema.

Input shape (from OW ``GET /api/v1/external/users/{id}/timeseries``)::

    {
        "timestamp": "2026-04-09T08:30:00+00:00",
        "type": "heart_rate_variability",
        "value": 42.5,
        "unit": "ms",
        "source": {...}    # optional
    }
"""

from omh_shim._dispatch import register
from omh_shim.sources._common import isoformat, parse_datetime


@register(source="ow_normalized", data_type="heart_rate_variability")
def convert(sample: dict) -> dict:
    timestamp = isoformat(parse_datetime(sample["timestamp"]))
    return {
        "heart_rate_variability": {"value": float(sample["value"]), "unit": "ms"},
        "effective_time_frame": {"date_time": timestamp},
    }
