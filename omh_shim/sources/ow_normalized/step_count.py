"""Convert an OW step-count input to ``omh:step-count:3.0``.

The OMH step-count schema requires ``effective_time_frame`` to contain a
``time_interval``, never a ``date_time``. Two input shapes are supported:

1. ``ActivitySummary`` shape (preferred — from OW summaries endpoint):
   ``{"date": "2026-04-09", "steps": 8432, "source": {...}}``. The
   ``effective_time_frame`` covers the full day.

2. ``TimeSeriesSample`` shape (from OW timeseries endpoint with
   ``type=steps``): ``{"timestamp": "...", "type": "steps", "value": 12,
   "unit": "steps", ...}``. Because the OMH schema rejects ``date_time``,
   the converter constructs a 1-minute interval ending at ``timestamp``
   (matching OW's per-minute resolution for step counts).
"""

from datetime import timedelta

from omh_shim._dispatch import register
from omh_shim.sources._common import day_interval, isoformat, parse_datetime


@register(source="ow_normalized", data_type="step_count")
def convert(sample: dict) -> dict:
    if "date" in sample:
        steps = sample["steps"]
        time_interval = day_interval(sample["date"])
    elif "timestamp" in sample and sample.get("type") == "steps":
        steps = sample["value"]
        end = parse_datetime(sample["timestamp"])
        start = end - timedelta(minutes=1)
        time_interval = {
            "start_date_time": isoformat(start),
            "end_date_time": isoformat(end),
        }
    else:
        raise KeyError(
            "step_count input must have either {'date', 'steps'} (ActivitySummary) "
            "or {'timestamp', 'type': 'steps', 'value'} (TimeSeriesSample) keys"
        )

    return {
        "step_count": {"value": steps, "unit": "steps"},
        "effective_time_frame": {"time_interval": time_interval},
    }
