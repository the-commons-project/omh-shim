"""Parameterized tests for the ``ow_normalized`` source converters.

One fixture pair per converter under ``tests/fixtures/ow_normalized/``.
``convert()`` validates each output against its target OMH schema by
default, so a green test is also a passing schema validation.
"""

import json
from pathlib import Path

import pytest

from omh_shim import convert

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ow_normalized"

DATA_TYPES = [
    "heart_rate",
    "heart_rate_variability",
    "step_count",
    "sleep_duration",
    "sleep_episode",
    "physical_activity",
]


@pytest.mark.parametrize("data_type", DATA_TYPES)
def test_ow_normalized_converter_matches_expected(data_type):
    sample = json.loads((FIXTURE_DIR / f"{data_type}_input.json").read_text())
    expected = json.loads((FIXTURE_DIR / f"{data_type}_expected.json").read_text())
    result = convert(source="ow_normalized", data_type=data_type, sample=sample)
    assert result == expected


def test_step_count_accepts_timeseries_shape():
    """Second supported input shape: a TimeSeriesSample with type=steps.

    The converter constructs a 1-minute time interval ending at ``timestamp``.
    """
    sample = {
        "timestamp": "2026-04-09T08:30:00+00:00",
        "type": "steps",
        "value": 12,
        "unit": "steps",
    }
    result = convert(source="ow_normalized", data_type="step_count", sample=sample)
    assert result["step_count"] == {"value": 12, "unit": "steps"}
    interval = result["effective_time_frame"]["time_interval"]
    assert interval["start_date_time"] == "2026-04-09T08:29:00Z"
    assert interval["end_date_time"] == "2026-04-09T08:30:00Z"


def test_step_count_rejects_unknown_shape():
    with pytest.raises(KeyError):
        convert(source="ow_normalized", data_type="step_count", sample={"foo": "bar"})


def test_physical_activity_omits_optional_fields_when_absent():
    sample = {"date": "2026-04-09", "steps": 100}
    result = convert(source="ow_normalized", data_type="physical_activity", sample=sample)
    assert "distance" not in result
    assert "kcal_burned" not in result
    assert result["activity_name"] == "daily activity summary"
