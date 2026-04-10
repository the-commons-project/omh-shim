"""Convert an Oura ``/v2/usercollection/daily_activity/data[i]`` item to
``omh:step-count:3.0``.

Mapping logic ported with permission from dicristea/oura-clinical-workbench
(data_syn/config/mapping_config.json::dailyactivitymodel_steps — mapped to
IEEE, extended here to the OMH step-count schema). See AUTHORS.md.

Input shape (from Oura v2 API)::

    {
        "day": "2026-04-09",
        "steps": 8432,
        "score": 85,
        "active_calories": 342,
        ...
    }

OMH's ``step-count:3.0`` requires ``effective_time_frame.time_interval``, so
the converter uses the day's UTC midnight bounds.
"""

from omh_shim._dispatch import register
from omh_shim.sources._common import day_interval


@register(source="oura_raw", data_type="step_count")
def convert(sample: dict) -> dict:
    return {
        "step_count": {"value": sample["steps"], "unit": "steps"},
        "effective_time_frame": {"time_interval": day_interval(sample["day"])},
    }
