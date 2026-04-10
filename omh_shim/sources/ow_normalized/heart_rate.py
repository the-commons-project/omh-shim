"""Convert an OW ``TimeSeriesSample`` (type=heart_rate) to ``omh:heart-rate:2.0``.

Input shape (from OW ``GET /api/v1/external/users/{id}/timeseries``)::

    {
        "timestamp": "2026-04-09T08:30:00+00:00",
        "zone_offset": "+00:00",        # optional
        "type": "heart_rate",
        "value": 72,
        "unit": "bpm",
        "source": {                     # optional
            "source_name": "Oura Ring",
            "device_model": "Oura Gen 3"
        }
    }
"""

from omh_shim._dispatch import register
from omh_shim.sources._common import isoformat, parse_datetime


@register(source="ow_normalized", data_type="heart_rate")
def convert(sample: dict) -> dict:
    timestamp = isoformat(parse_datetime(sample["timestamp"]))
    return {
        "heart_rate": {"value": sample["value"], "unit": "beats/min"},
        "effective_time_frame": {"date_time": timestamp},
    }
