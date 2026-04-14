"""Tests for omh-shim.

Test fixtures live in ``tests/fixtures/<source>/<data_type>_{input,expected}.json``.
Every converter output is validated against its target OMH schema — the library
itself ships without jsonschema, so runtime validation is a test-time concern.
"""

import importlib.resources
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from jsonschema import Draft7Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

from omh_shim import SCHEMA_IDS, ConvertError, to_omh
from omh_shim import _day_interval as day_interval
from omh_shim import _parse_dt as parse_datetime

FIXTURES = Path(__file__).parent / "fixtures"

DATA_TYPES = [
    "heart_rate",
    "heart_rate_variability",
    "step_count",
    "sleep_duration",
    "sleep_episode",
    "physical_activity",
]
SOURCES = ["oura_raw", "ow_normalized"]


# ---------------------------------------------------------------------------
# Schema validation infrastructure (test-only; library doesn't ship this)
# ---------------------------------------------------------------------------

_FILENAMES = {
    "omh:heart-rate:2.0": "omh_heart-rate_2-0.json",
    "local:heart-rate-variability:1.0": "local_heart-rate-variability_1-0.json",
    "omh:step-count:3.0": "omh_step-count_3-0.json",
    "omh:sleep-duration:2.0": "omh_sleep-duration_2-0.json",
    "omh:sleep-episode:1.1": "omh_sleep-episode_1-1.json",
    "omh:physical-activity:1.2": "omh_physical-activity_1-2.json",
    "omh:oxygen-saturation:2.0": "omh_oxygen-saturation_2-0.json",
}


def _validator(schema_id: str) -> Draft7Validator:
    schemas_pkg = importlib.resources.files("omh_shim.schemas")
    resources = []
    for entry in schemas_pkg.iterdir():
        if entry.name.endswith(".json"):
            with entry.open("r", encoding="utf-8") as f:
                resources.append(
                    (entry.name, Resource.from_contents(json.load(f), default_specification=DRAFT7))
                )
    with schemas_pkg.joinpath(_FILENAMES[schema_id]).open("r", encoding="utf-8") as f:
        return Draft7Validator(json.load(f), registry=Registry().with_resources(resources))


def _assert_valid(body: dict, schema_id: str) -> None:
    errors = sorted(_validator(schema_id).iter_errors(body), key=lambda e: list(e.absolute_path))
    assert not errors, f"Schema violations for {schema_id}: " + "; ".join(
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors
    )


# ---------------------------------------------------------------------------
# Fixture-driven converter tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize("data_type", DATA_TYPES)
def test_converter_matches_expected(source, data_type):
    fx = FIXTURES / source
    sample = json.loads((fx / f"{data_type}_input.json").read_text())
    expected = json.loads((fx / f"{data_type}_expected.json").read_text())
    result = to_omh(source, data_type, sample, tz=UTC)
    assert result["body"] == expected
    _assert_valid(result["body"], SCHEMA_IDS[data_type])


# ---------------------------------------------------------------------------
# Source-specific edge cases
# ---------------------------------------------------------------------------


def test_oura_hrv_rejects_normalized_score():
    sample = {"day": "2026-04-09", "score": 85, "contributors": {"hrv_balance": 70}}
    with pytest.raises(ConvertError, match="rmssd"):
        to_omh("oura_raw", "heart_rate_variability", sample)


def test_oura_sleep_episode_nap_is_not_main_sleep():
    sample = {
        "bedtime_start": "2026-04-09T13:00:00+00:00",
        "bedtime_end": "2026-04-09T13:45:00+00:00",
        "total_sleep_duration": 2400,
        "type": "nap",
    }
    assert to_omh("oura_raw", "sleep_episode", sample)["body"]["is_main_sleep"] is False


def test_ow_step_count_accepts_timeseries_shape():
    sample = {"timestamp": "2026-04-09T08:30:00+00:00", "type": "steps", "value": 12}
    body = to_omh("ow_normalized", "step_count", sample)["body"]
    assert body["step_count"] == {"value": 12, "unit": "steps"}
    assert body["effective_time_frame"]["time_interval"] == {
        "start_date_time": "2026-04-09T08:29:00Z",
        "end_date_time": "2026-04-09T08:30:00Z",
    }


def test_ow_step_count_rejects_unknown_shape():
    with pytest.raises(ConvertError):
        to_omh("ow_normalized", "step_count", {"foo": "bar"}, tz=UTC)


@pytest.mark.parametrize(
    "source,sample",
    [
        ("oura_raw", {"day": "2026-04-09"}),
        ("ow_normalized", {"date": "2026-04-09", "steps": 100}),
    ],
)
def test_physical_activity_omits_optional_fields_when_absent(source, sample):
    body = to_omh(source, "physical_activity", sample, tz=UTC)["body"]
    assert "distance" not in body
    assert "kcal_burned" not in body
    assert body["activity_name"] == "daily activity summary"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def test_unknown_pair_raises():
    with pytest.raises(ConvertError):
        to_omh("ow_normalized", "not_a_real_type", {})


@pytest.mark.parametrize(
    "sample",
    [
        {},  # KeyError: missing 'bpm'
        {"bpm": None, "timestamp": "2026-04-09T08:00:00Z"},  # TypeError: float(None)
    ],
)
def test_converter_errors_wrapped_as_convert_error(sample):
    with pytest.raises(ConvertError):
        to_omh("oura_raw", "heart_rate", sample)


def test_schema_ids_are_read_only():
    with pytest.raises(TypeError):
        SCHEMA_IDS["heart_rate"] = "mutated"  # type: ignore[index]


# ---------------------------------------------------------------------------
# Datetime parsing
# ---------------------------------------------------------------------------


def test_parse_datetime_rejects_naive():
    with pytest.raises(ConvertError, match="timezone"):
        parse_datetime("2026-04-09T08:30:00")


def test_parse_datetime_accepts_utc_Z():
    assert parse_datetime("2026-04-09T08:30:00Z").utcoffset().total_seconds() == 0


def test_parse_datetime_accepts_offset():
    assert parse_datetime("2026-04-09T08:30:00-07:00").utcoffset().total_seconds() == -7 * 3600


def test_parse_datetime_rejects_garbage():
    with pytest.raises(ConvertError):
        parse_datetime("not a datetime")


# ---------------------------------------------------------------------------
# Day intervals
# ---------------------------------------------------------------------------


def test_day_interval_requires_tz():
    with pytest.raises(ConvertError, match="timezone"):
        day_interval("2026-04-09", tz=None)


_LA = ZoneInfo("America/Los_Angeles")


@pytest.mark.parametrize(
    "date_str,tz,expected",
    [
        # Basic UTC
        ("2026-04-09", UTC, ("2026-04-09T00:00:00Z", "2026-04-10T00:00:00Z")),
        # Non-UTC timezone
        ("2026-04-09", _LA, ("2026-04-09T00:00:00-07:00", "2026-04-10T00:00:00-07:00")),
        # DST spring forward: PST -> PDT
        ("2026-03-08", _LA, ("2026-03-08T00:00:00-08:00", "2026-03-09T00:00:00-07:00")),
        # DST fall back: PDT -> PST
        ("2026-11-01", _LA, ("2026-11-01T00:00:00-07:00", "2026-11-02T00:00:00-08:00")),
    ],
    ids=["utc", "non_utc", "spring_forward", "fall_back"],
)
def test_day_interval(date_str, tz, expected):
    assert day_interval(date_str, tz=tz) == {
        "start_date_time": expected[0],
        "end_date_time": expected[1],
    }


# ---------------------------------------------------------------------------
# Timezone handling
# ---------------------------------------------------------------------------

DAILY_CASES = [
    ("oura_raw", "step_count", {"day": "2026-04-09", "steps": 100}),
    ("oura_raw", "physical_activity", {"day": "2026-04-09"}),
    ("ow_normalized", "step_count", {"date": "2026-04-09", "steps": 100}),
    ("ow_normalized", "physical_activity", {"date": "2026-04-09"}),
    (
        "ow_normalized",
        "sleep_duration",
        {"date": "2026-04-09", "sleep_total_duration_minutes": 480},
    ),
]


@pytest.mark.parametrize("source,data_type,sample", DAILY_CASES)
def test_daily_types_require_tz(source, data_type, sample):
    with pytest.raises(ConvertError, match="timezone"):
        to_omh(source, data_type, sample)


@pytest.mark.parametrize("source,data_type,sample", DAILY_CASES)
@pytest.mark.parametrize(
    "tz,expected_start",
    [(UTC, "2026-04-09T00:00:00Z"), (ZoneInfo("America/Los_Angeles"), "2026-04-09T00:00:00-07:00")],
)
def test_daily_types_respect_tz(source, data_type, sample, tz, expected_start):
    body = to_omh(source, data_type, sample, tz=tz)["body"]
    assert body["effective_time_frame"]["time_interval"]["start_date_time"] == expected_start


NAIVE_CASES = [
    ("oura_raw", "heart_rate", {"bpm": 72, "timestamp": "2026-04-09T08:30:00"}),
    ("oura_raw", "heart_rate_variability", {"rmssd": 45.0, "timestamp": "2026-04-09T08:30:00"}),
    (
        "oura_raw",
        "sleep_duration",
        {
            "total_sleep_duration": 27000,
            "bedtime_start": "2026-04-09T22:00:00",
            "bedtime_end": "2026-04-10T06:00:00",
        },
    ),
    (
        "oura_raw",
        "sleep_episode",
        {"bedtime_start": "2026-04-09T22:00:00", "bedtime_end": "2026-04-10T06:00:00"},
    ),
    (
        "ow_normalized",
        "heart_rate",
        {"timestamp": "2026-04-09T08:30:00", "type": "heart_rate", "value": 72},
    ),
    (
        "ow_normalized",
        "heart_rate_variability",
        {"timestamp": "2026-04-09T08:30:00", "type": "heart_rate_variability", "value": 45.0},
    ),
    (
        "ow_normalized",
        "sleep_episode",
        {"bedtime_start": "2026-04-09T22:00:00", "bedtime_end": "2026-04-10T06:00:00"},
    ),
    (
        "ow_normalized",
        "step_count",
        {"timestamp": "2026-04-09T08:30:00", "type": "steps", "value": 10},
    ),
]


@pytest.mark.parametrize("source,data_type,sample", NAIVE_CASES)
def test_rejects_naive_datetime(source, data_type, sample):
    with pytest.raises(ConvertError, match="timezone"):
        to_omh(source, data_type, sample)


# ---------------------------------------------------------------------------
# Numeric precision
# ---------------------------------------------------------------------------


def test_fractional_bpm_preserved():
    body = to_omh("oura_raw", "heart_rate", {"bpm": 72.456, "timestamp": "2026-04-09T08:00:00Z"})[
        "body"
    ]
    assert body["heart_rate"]["value"] == 72.456


def test_ow_sleep_duration_fractional_minutes():
    """32.5 minutes -> 1950 seconds (not 1920 from int-then-scale)."""
    body = to_omh(
        "ow_normalized",
        "sleep_duration",
        {"date": "2026-04-09", "sleep_total_duration_minutes": 32.5},
        tz=UTC,
    )["body"]
    assert body["sleep_duration"]["value"] == 1950


# ---------------------------------------------------------------------------
# Header envelope (IEEE 1752.1)
# ---------------------------------------------------------------------------


def test_header_structure():
    """IEEE 1752.1 header: uuid, parsed schema_id, source_creation_date_time,
    modality=sensed. acquisition_provenance (older OMH schema) must NOT appear."""
    result = to_omh(
        "ow_normalized",
        "heart_rate",
        {"timestamp": "2026-04-09T08:00:00Z", "type": "heart_rate", "value": 72},
    )
    assert set(result) == {"header", "body"}
    h = result["header"]
    uuid.UUID(h["uuid"])  # raises ValueError if invalid
    assert h["schema_id"] == {"namespace": "omh", "name": "heart-rate", "version": "2.0"}
    assert h["modality"] == "sensed"
    datetime.fromisoformat(h["source_creation_date_time"].replace("Z", "+00:00"))
    assert "acquisition_provenance" not in h
    assert "external_datasheets" not in h  # no sample["source"] -> omitted


def test_header_external_datasheets_from_source_metadata():
    result = to_omh(
        "oura_raw",
        "heart_rate",
        {"bpm": 72, "timestamp": "2026-04-09T08:00:00Z", "source": {"device": "Oura Ring Gen3"}},
    )
    assert result["header"]["external_datasheets"] == [
        {"datasheet_type": "manufacturer", "datasheet_reference": "Oura Ring Gen3"},
    ]


def test_header_local_namespace_for_hrv():
    result = to_omh(
        "oura_raw",
        "heart_rate_variability",
        {"rmssd": 42.5, "timestamp": "2026-04-09T08:00:00Z"},
    )
    assert result["header"]["schema_id"] == {
        "namespace": "local",
        "name": "heart-rate-variability",
        "version": "1.0",
    }
