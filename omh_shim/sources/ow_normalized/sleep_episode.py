"""Convert an OW sleep details object to ``omh:sleep-episode:1.1``.

Input shape (from OW sleep events / sleep detail endpoint)::

    {
        "record_id": "uuid",
        "bedtime_start": "2026-04-09T22:30:00+00:00",
        "bedtime_end": "2026-04-10T06:45:00+00:00",
        "sleep_total_duration_minutes": 460,        # optional
        "sleep_time_in_bed_minutes": 495,           # optional
        "sleep_deep_minutes": 95,                   # optional
        "sleep_rem_minutes": 110,                   # optional
        "sleep_light_minutes": 255,                 # optional
        "sleep_awake_minutes": 35,                  # optional
        "is_nap": false,                            # optional
        "sleep_efficiency_score": 92.5,             # optional, 0-100
    }

The OMH ``sleep-episode:1.1`` schema only *requires* ``effective_time_frame``
with a ``time_interval``. Everything else is optional, so we populate as much
as the input contains. The schema deliberately does NOT carry per-stage
breakdowns; downstream consumers wanting stage-level detail should look at
the OMH sleep-stage-summary schemas (not in v0.1 scope).
"""

from omh_shim._dispatch import register
from omh_shim.sources._common import time_interval_from_bounds


@register(source="ow_normalized", data_type="sleep_episode")
def convert(sample: dict) -> dict:
    output: dict = {
        "effective_time_frame": {
            "time_interval": time_interval_from_bounds(
                sample["bedtime_start"], sample["bedtime_end"]
            )
        }
    }

    if "sleep_total_duration_minutes" in sample and sample["sleep_total_duration_minutes"] is not None:
        output["total_sleep_time"] = {
            "value": int(sample["sleep_total_duration_minutes"]) * 60,
            "unit": "sec",
        }

    if "sleep_awake_minutes" in sample and sample["sleep_awake_minutes"] is not None:
        output["wake_after_sleep_onset"] = {
            "value": int(sample["sleep_awake_minutes"]) * 60,
            "unit": "sec",
        }

    if "is_nap" in sample and sample["is_nap"] is not None:
        output["is_main_sleep"] = not bool(sample["is_nap"])

    if "sleep_efficiency_score" in sample and sample["sleep_efficiency_score"] is not None:
        output["sleep_maintenance_efficiency_percentage"] = {
            "value": float(sample["sleep_efficiency_score"]),
            "unit": "%",
        }

    return output
