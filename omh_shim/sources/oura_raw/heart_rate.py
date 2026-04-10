"""Convert an Oura ``/v2/usercollection/heartrate/data[i]`` item to ``omh:heart-rate:2.0``.

Mapping logic ported with permission from dicristea/oura-clinical-workbench
(data_syn/utils/record_builder.py::build_heart_rate_measurement). See AUTHORS.md.

Input shape (from Oura v2 API)::

    {
        "bpm": 72,
        "source": "sleep",                      # or "awake", "rest", ...
        "timestamp": "2026-04-09T03:15:00+00:00"
    }

Oura's heart rate endpoint returns per-moment samples. The ``source`` string
is Oura's own label for *context* (sleep / awake / rest), not device model.
It's preserved only in the optional descriptive fields we don't currently
emit — it's not lost upstream because OW wraps it under its own ``source``
metadata when ingesting.
"""

from omh_shim._dispatch import register
from omh_shim.sources._common import isoformat, parse_datetime


@register(source="oura_raw", data_type="heart_rate")
def convert(sample: dict) -> dict:
    bpm = sample["bpm"]
    timestamp = isoformat(parse_datetime(sample["timestamp"]))
    return {
        "heart_rate": {"value": round(float(bpm), 1), "unit": "beats/min"},
        "effective_time_frame": {"date_time": timestamp},
    }
