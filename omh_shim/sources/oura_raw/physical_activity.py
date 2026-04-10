"""Convert an Oura ``/v2/usercollection/daily_activity/data[i]`` item to
``omh:physical-activity:1.2``.

Mapping logic ported with permission from dicristea/oura-clinical-workbench
(data_syn/config/mapping_config.json::dailyactivitymodel_active_calories maps
active_calories -> omh:calories-burned:2.0; this converter extends it to the
physical-activity schema which is our v0.1 target). See AUTHORS.md.

Input shape (from Oura v2 API ``/v2/usercollection/daily_activity/data[i]``)::

    {
        "day": "2026-04-09",
        "active_calories": 342,
        "total_calories": 2100,
        "equivalent_walking_distance": 6240,   # meters
        "low_activity_time": 4500,             # seconds
        "medium_activity_time": 1200,          # seconds
        "high_activity_time": 300,             # seconds
        "steps": 8432,
        "score": 85,
        ...
    }

The OMH ``physical-activity:1.2`` schema only requires ``activity_name``.
Optional fields populated when the Oura input has them: ``distance`` (from
``equivalent_walking_distance``), ``kcal_burned`` (from ``active_calories``).
"""

from omh_shim._dispatch import register
from omh_shim.sources._common import day_interval


@register(source="oura_raw", data_type="physical_activity")
def convert(sample: dict) -> dict:
    output: dict = {
        "activity_name": "daily activity summary",
        "effective_time_frame": {"time_interval": day_interval(sample["day"])},
    }

    if "equivalent_walking_distance" in sample and sample["equivalent_walking_distance"] is not None:
        output["distance"] = {
            "value": float(sample["equivalent_walking_distance"]),
            "unit": "m",
        }

    if "active_calories" in sample and sample["active_calories"] is not None:
        output["kcal_burned"] = {
            "value": float(sample["active_calories"]),
            "unit": "kcal",
        }

    return output
