"""Convert an Oura ``/v2/usercollection/sleep/data[i]`` item to
``omh:sleep-duration:2.0``.

Mapping logic ported with permission from dicristea/oura-clinical-workbench
(data_syn/config/mapping_config.json::sleepmodel_total_sleep_duration maps
this to omh:total-sleep-time:1.0, which is semantically equivalent but
outside our v0.1 target schema set). See AUTHORS.md.

Input shape (from Oura v2 API)::

    {
        "bedtime_start": "2026-04-09T22:30:00+00:00",
        "bedtime_end": "2026-04-10T06:45:00+00:00",
        "total_sleep_duration": 27600,   # seconds
        "time_in_bed": 29700,            # seconds
        ...
    }

OMH's ``sleep-duration:2.0`` requires ``effective_time_frame.time_interval``,
which the converter builds from ``bedtime_start``/``bedtime_end``. Oura
already reports ``total_sleep_duration`` in seconds, so no unit conversion.
"""

from omh_shim._dispatch import register
from omh_shim.sources._common import time_interval_from_bounds


@register(source="oura_raw", data_type="sleep_duration")
def convert(sample: dict) -> dict:
    return {
        "sleep_duration": {"value": int(sample["total_sleep_duration"]), "unit": "sec"},
        "effective_time_frame": {
            "time_interval": time_interval_from_bounds(
                sample["bedtime_start"], sample["bedtime_end"]
            )
        },
    }
