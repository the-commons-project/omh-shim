"""Parameterized tests for the ``oura_raw`` source converters.

One fixture pair per converter under ``tests/fixtures/oura_raw/``.
``convert()`` validates each output against its target OMH schema by
default, so a green test is also a passing schema validation.
"""

import json
from pathlib import Path

import pytest

from omh_shim import convert

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "oura_raw"

DATA_TYPES = [
    "heart_rate",
    "heart_rate_variability",
    "step_count",
    "sleep_duration",
    "sleep_episode",
    "physical_activity",
]


@pytest.mark.parametrize("data_type", DATA_TYPES)
def test_oura_raw_converter_matches_expected(data_type):
    sample = json.loads((FIXTURE_DIR / f"{data_type}_input.json").read_text())
    expected = json.loads((FIXTURE_DIR / f"{data_type}_expected.json").read_text())
    result = convert(source="oura_raw", data_type=data_type, sample=sample)
    assert result == expected


def test_heart_rate_variability_rejects_normalized_score():
    """Oura's daily_readiness contributors.hrv_balance is a 0-100 score, not ms.

    The converter must refuse to silently treat it as a millisecond value.
    """
    sample = {
        "day": "2026-04-09",
        "score": 85,
        "contributors": {"hrv_balance": 70},
    }
    with pytest.raises(KeyError, match="rmssd"):
        convert(source="oura_raw", data_type="heart_rate_variability", sample=sample)


def test_sleep_episode_nap_is_not_main_sleep():
    sample = {
        "id": "nap-1",
        "bedtime_start": "2026-04-09T13:00:00+00:00",
        "bedtime_end": "2026-04-09T13:45:00+00:00",
        "total_sleep_duration": 2400,
        "type": "nap",
    }
    result = convert(source="oura_raw", data_type="sleep_episode", sample=sample)
    assert result["is_main_sleep"] is False


def test_physical_activity_omits_optional_fields_when_absent():
    sample = {"day": "2026-04-09"}
    result = convert(source="oura_raw", data_type="physical_activity", sample=sample)
    assert "distance" not in result
    assert "kcal_burned" not in result
