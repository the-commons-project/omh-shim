"""Core behavior tests for omh-shim.

Tests are written as specification — they assert correct behavior, and the
code must pass them. Not the other way around.
"""

from datetime import UTC
from zoneinfo import ZoneInfo

import pytest

from omh_shim import SCHEMA_IDS, ConversionError, ValidationError, convert
from omh_shim._helpers import day_interval, parse_datetime

# --- public API ---


def test_convert_unknown_pair_raises_conversion_error():
    with pytest.raises(ConversionError):
        convert(source="ow_normalized", data_type="not_a_real_type", sample={})


# --- parse_datetime ---


def test_parse_datetime_rejects_naive():
    with pytest.raises(ConversionError, match="timezone"):
        parse_datetime("2026-04-09T08:30:00")


def test_parse_datetime_accepts_utc_Z():
    dt = parse_datetime("2026-04-09T08:30:00Z")
    assert dt.utcoffset().total_seconds() == 0


def test_parse_datetime_accepts_offset():
    dt = parse_datetime("2026-04-09T08:30:00-07:00")
    assert dt.utcoffset().total_seconds() == -7 * 3600


def test_parse_datetime_rejects_garbage():
    with pytest.raises(ConversionError):
        parse_datetime("not a datetime")


# --- day_interval ---


def test_day_interval_requires_tz():
    with pytest.raises(ConversionError, match="timezone"):
        day_interval("2026-04-09", tz=None)


def test_day_interval_utc():
    assert day_interval("2026-04-09", tz=UTC) == {
        "start_date_time": "2026-04-09T00:00:00Z",
        "end_date_time": "2026-04-10T00:00:00Z",
    }


def test_day_interval_non_utc():
    assert day_interval("2026-04-09", tz=ZoneInfo("America/Los_Angeles")) == {
        "start_date_time": "2026-04-09T00:00:00-07:00",
        "end_date_time": "2026-04-10T00:00:00-07:00",
    }


def test_day_interval_spring_forward():
    """March 8 2026 LA: PST -> PDT. Offset changes from -08 to -07."""
    assert day_interval("2026-03-08", tz=ZoneInfo("America/Los_Angeles")) == {
        "start_date_time": "2026-03-08T00:00:00-08:00",
        "end_date_time": "2026-03-09T00:00:00-07:00",
    }


def test_day_interval_fall_back():
    """Nov 1 2026 LA: PDT -> PST. Offset changes from -07 to -08."""
    assert day_interval("2026-11-01", tz=ZoneInfo("America/Los_Angeles")) == {
        "start_date_time": "2026-11-01T00:00:00-07:00",
        "end_date_time": "2026-11-02T00:00:00-08:00",
    }


# --- convert() error wrapping ---


def test_convert_wraps_missing_field():
    with pytest.raises(ConversionError):
        convert(source="oura_raw", data_type="heart_rate", sample={})


def test_convert_wraps_type_error():
    with pytest.raises(ConversionError):
        convert(
            source="oura_raw",
            data_type="heart_rate",
            sample={"bpm": None, "timestamp": "2026-04-09T08:00:00Z"},
        )


# --- tz required for daily types ---


DAILY_CASES = [
    ("oura_raw", "step_count", {"day": "2026-04-09", "steps": 100}),
    ("oura_raw", "physical_activity", {"day": "2026-04-09"}),
    ("ow_normalized", "step_count", {"date": "2026-04-09", "steps": 100}),
    ("ow_normalized", "physical_activity", {"date": "2026-04-09"}),
    ("ow_normalized", "sleep_duration", {"date": "2026-04-09", "sleep_total_duration_minutes": 480}),
]


@pytest.mark.parametrize("source,data_type,sample", DAILY_CASES)
def test_daily_types_require_tz(source, data_type, sample):
    with pytest.raises(ConversionError, match="timezone"):
        convert(source=source, data_type=data_type, sample=sample)


@pytest.mark.parametrize("source,data_type,sample", DAILY_CASES)
def test_daily_types_accept_utc(source, data_type, sample):
    result = convert(source=source, data_type=data_type, sample=sample, tz=UTC)
    interval = result["effective_time_frame"]["time_interval"]
    assert interval["start_date_time"] == "2026-04-09T00:00:00Z"


@pytest.mark.parametrize("source,data_type,sample", DAILY_CASES)
def test_daily_types_respect_non_utc_tz(source, data_type, sample):
    result = convert(source=source, data_type=data_type, sample=sample,
                     tz=ZoneInfo("America/Los_Angeles"))
    interval = result["effective_time_frame"]["time_interval"]
    assert interval["start_date_time"] == "2026-04-09T00:00:00-07:00"


# --- naive datetime rejection across all timestamp converters ---


NAIVE_CASES = [
    ("oura_raw", "heart_rate", {"bpm": 72, "timestamp": "2026-04-09T08:30:00"}),
    ("oura_raw", "heart_rate_variability", {"rmssd": 45.0, "timestamp": "2026-04-09T08:30:00"}),
    ("oura_raw", "sleep_duration", {"total_sleep_duration": 27000,
     "bedtime_start": "2026-04-09T22:00:00", "bedtime_end": "2026-04-10T06:00:00"}),
    ("oura_raw", "sleep_episode", {"bedtime_start": "2026-04-09T22:00:00",
     "bedtime_end": "2026-04-10T06:00:00"}),
    ("ow_normalized", "heart_rate", {"timestamp": "2026-04-09T08:30:00",
     "type": "heart_rate", "value": 72}),
    ("ow_normalized", "heart_rate_variability", {"timestamp": "2026-04-09T08:30:00",
     "type": "heart_rate_variability", "value": 45.0}),
    ("ow_normalized", "sleep_episode", {"bedtime_start": "2026-04-09T22:00:00",
     "bedtime_end": "2026-04-10T06:00:00"}),
    ("ow_normalized", "step_count", {"timestamp": "2026-04-09T08:30:00",
     "type": "steps", "value": 10}),
]


@pytest.mark.parametrize("source,data_type,sample", NAIVE_CASES)
def test_rejects_naive_datetime(source, data_type, sample):
    with pytest.raises(ConversionError, match="timezone"):
        convert(source=source, data_type=data_type, sample=sample)


# --- converters raise ConversionError directly (not raw KeyError) ---


def test_oura_hrv_rejects_normalized_score_directly():
    from omh_shim.sources import oura_raw
    with pytest.raises(ConversionError, match="rmssd"):
        oura_raw.heart_rate_variability(
            {"day": "2026-04-09", "contributors": {"hrv_balance": 70}}, tz=None)


def test_ow_step_count_rejects_unknown_shape_directly():
    from omh_shim.sources import ow_normalized
    with pytest.raises(ConversionError):
        ow_normalized.step_count({"foo": "bar"}, tz=UTC)


# --- schema validation ---


def test_validation_passes_valid():
    from omh_shim._validate import validate_output
    validate_output(
        {"heart_rate": {"value": 72, "unit": "beats/min"},
         "effective_time_frame": {"date_time": "2026-04-09T08:00:00Z"}},
        "omh:heart-rate:2.0",
    )


def test_validation_rejects_empty():
    from omh_shim._validate import validate_output
    with pytest.raises(ValidationError):
        validate_output({}, "omh:heart-rate:2.0")


def test_all_schemas_load():
    from omh_shim._schema_loader import load
    for schema_id in SCHEMA_IDS.values():
        assert isinstance(load(schema_id), dict)


def test_hrv_schema_is_local_namespace():
    assert SCHEMA_IDS["heart_rate_variability"].startswith("local:")


# --- numeric precision ---


def test_oura_heart_rate_preserves_fractional_bpm():
    result = convert(source="oura_raw", data_type="heart_rate",
                     sample={"bpm": 72.456, "timestamp": "2026-04-09T08:00:00Z"})
    assert result["heart_rate"]["value"] == 72.456


def test_ow_sleep_duration_fractional_minutes():
    """32.5 minutes -> 1950 seconds (not 1920 from int-then-scale)."""
    result = convert(source="ow_normalized", data_type="sleep_duration",
                     sample={"date": "2026-04-09", "sleep_total_duration_minutes": 32.5},
                     tz=UTC)
    assert result["sleep_duration"]["value"] == 1950


# --- validate kwarg ---


def test_validate_false_skips(monkeypatch):
    from omh_shim import _validate
    monkeypatch.setattr(_validate, "validate_output",
                        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not call")))
    result = convert(source="ow_normalized", data_type="heart_rate",
                     sample={"timestamp": "2026-04-09T08:00:00Z",
                             "type": "heart_rate", "value": 72},
                     validate=False)
    assert result["heart_rate"]["value"] == 72
