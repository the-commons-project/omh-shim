"""Convert an OW ``ActivitySummary`` (with sleep fields) to ``omh:sleep-duration:2.0``.

Input shape (from OW ``GET /api/v1/external/users/{id}/summaries``)::

    {
        "date": "2026-04-09",
        "sleep_total_duration_minutes": 432,
        "sleep_time_in_bed_minutes": 480,    # optional
        "source": {...}                       # optional
    }

The OMH schema requires ``effective_time_frame`` to contain a ``time_interval``
(not a ``date_time``). The converter uses the day's UTC midnight bounds.
"""

from omh_shim._dispatch import register
from omh_shim.sources._common import day_interval


@register(source="ow_normalized", data_type="sleep_duration")
def convert(sample: dict) -> dict:
    minutes = sample["sleep_total_duration_minutes"]
    return {
        "sleep_duration": {"value": int(minutes) * 60, "unit": "sec"},
        "effective_time_frame": {"time_interval": day_interval(sample["date"])},
    }
