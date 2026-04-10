"""Convert an OW ``ActivitySummary`` to ``omh:physical-activity:1.2``.

Input shape (from OW ``GET /api/v1/external/users/{id}/summaries``)::

    {
        "date": "2026-04-09",
        "steps": 8432,
        "distance_meters": 6240.5,
        "active_calories_kcal": 342.5,
        "active_minutes": 60,
        "source": {...}                        # optional
    }

The OMH ``physical-activity:1.2`` schema requires only ``activity_name``;
everything else is optional. We always emit ``activity_name`` ("daily activity
summary"), ``effective_time_frame`` (the day), and any of ``distance``,
``kcal_burned`` that the input carries. There is no field on the OMH schema
for step count or active minutes — step counts go through the dedicated
``step_count`` converter, and active minutes are not modeled here.
"""

from omh_shim._dispatch import register
from omh_shim.sources._common import day_interval


@register(source="ow_normalized", data_type="physical_activity")
def convert(sample: dict) -> dict:
    output: dict = {
        "activity_name": "daily activity summary",
        "effective_time_frame": {"time_interval": day_interval(sample["date"])},
    }

    if "distance_meters" in sample and sample["distance_meters"] is not None:
        output["distance"] = {"value": float(sample["distance_meters"]), "unit": "m"}

    if "active_calories_kcal" in sample and sample["active_calories_kcal"] is not None:
        output["kcal_burned"] = {"value": float(sample["active_calories_kcal"]), "unit": "kcal"}

    return output
