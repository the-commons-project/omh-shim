"""Convert an Oura ``/v2/usercollection/sleep/data[i]`` item to ``omh:sleep-episode:1.1``.

Mapping logic ported with permission from dicristea/oura-clinical-workbench
(data_syn/config/mapping_config.json entries under sleepmodel_*). dicristea's
mapping config covers bedtime_start, bedtime_end, awake_time, efficiency, and
time_in_bed for this schema. See AUTHORS.md.

Input shape (from Oura v2 API ``/v2/usercollection/sleep/data[i]``)::

    {
        "id": "uuid",
        "bedtime_start": "2026-04-09T22:30:00+00:00",
        "bedtime_end": "2026-04-10T06:45:00+00:00",
        "total_sleep_duration": 27600,   # seconds
        "time_in_bed": 29700,            # seconds
        "awake_time": 2100,              # seconds
        "efficiency": 92.5,              # 0-100 percentage
        "type": "long_sleep",            # or "short_sleep", "nap"
        "latency": 540,                  # seconds to sleep onset, optional
        ...
    }

OMH's ``sleep-episode:1.1`` requires only ``effective_time_frame``. Everything
else is optional. The converter populates every optional field that maps 1:1.
"""

from omh_shim._dispatch import register
from omh_shim.sources._common import time_interval_from_bounds


@register(source="oura_raw", data_type="sleep_episode")
def convert(sample: dict) -> dict:
    output: dict = {
        "effective_time_frame": {
            "time_interval": time_interval_from_bounds(
                sample["bedtime_start"], sample["bedtime_end"]
            )
        }
    }

    if "total_sleep_duration" in sample and sample["total_sleep_duration"] is not None:
        output["total_sleep_time"] = {
            "value": int(sample["total_sleep_duration"]),
            "unit": "sec",
        }

    if "awake_time" in sample and sample["awake_time"] is not None:
        output["wake_after_sleep_onset"] = {
            "value": int(sample["awake_time"]),
            "unit": "sec",
        }

    if "latency" in sample and sample["latency"] is not None:
        output["latency_to_sleep_onset"] = {
            "value": int(sample["latency"]),
            "unit": "sec",
        }

    if "type" in sample and sample["type"] is not None:
        # Oura's "long_sleep" and "short_sleep" are both main sleep; only
        # "nap" is explicitly not a main sleep event.
        output["is_main_sleep"] = sample["type"] != "nap"

    if "efficiency" in sample and sample["efficiency"] is not None:
        output["sleep_maintenance_efficiency_percentage"] = {
            "value": float(sample["efficiency"]),
            "unit": "%",
        }

    return output
