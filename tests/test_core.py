"""Smoke + unit tests for the core primitives.

These tests specify how omh-shim SHOULD behave; the code must match. In
particular, the timezone rules (no silent UTC coercion, explicit tz for
daily data types) and the exception contract (ConversionError on any
invalid input, not raw KeyError) are behavioral requirements — not
implementation details.
"""

from datetime import UTC
from zoneinfo import ZoneInfo

import pytest

from omh_shim import ConversionError, ValidationError, convert
from omh_shim._dispatch import lookup
from omh_shim._helpers import day_interval, parse_datetime

# --- public API surface ---


def test_package_exports_public_api():
    assert callable(convert)
    assert issubclass(ConversionError, Exception)
    assert issubclass(ValidationError, Exception)


def test_lookup_unknown_pair_raises_conversion_error():
    with pytest.raises(ConversionError) as exc_info:
        lookup("nope_source", "nope_data_type")
    msg = str(exc_info.value)
    assert "nope_source" in msg
    assert "nope_data_type" in msg


def test_convert_unknown_pair_raises_conversion_error():
    with pytest.raises(ConversionError):
        convert(source="ow_normalized", data_type="not_a_real_type", sample={})


# --- timezone handling: parse_datetime must reject naive datetimes ---


def test_parse_datetime_rejects_naive_string():
    """Silent UTC coercion of naive datetimes is a clinical-data footgun —
    a Tokyo user's "22:30" must not be recorded as UTC."""
    with pytest.raises(ConversionError, match="timezone"):
        parse_datetime("2026-04-09T08:30:00")


def test_parse_datetime_accepts_explicit_utc_Z():
    dt = parse_datetime("2026-04-09T08:30:00Z")
    assert dt.tzinfo is not None
    assert dt.utcoffset().total_seconds() == 0


def test_parse_datetime_accepts_explicit_offset():
    dt = parse_datetime("2026-04-09T08:30:00-07:00")
    assert dt.tzinfo is not None
    assert dt.utcoffset().total_seconds() == -7 * 3600


def test_parse_datetime_rejects_garbage():
    with pytest.raises(ConversionError):
        parse_datetime("not a datetime")


# --- timezone handling: day_interval requires explicit tz ---


def test_day_interval_requires_tz():
    """A 'day' in Tokyo is not a 'day' in UTC — silent UTC default would
    misalign daily summaries by up to 24 hours."""
    with pytest.raises(ConversionError, match="timezone"):
        day_interval("2026-04-09", tz=None)


def test_day_interval_utc_produces_utc_midnight_bounds():
    result = day_interval("2026-04-09", tz=UTC)
    assert result == {
        "start_date_time": "2026-04-09T00:00:00Z",
        "end_date_time": "2026-04-10T00:00:00Z",
    }


def test_day_interval_zoneinfo_utc_matches_datetime_utc():
    """Both datetime.UTC and ZoneInfo('UTC') must produce the same output —
    consumers should be free to pass either."""
    assert day_interval("2026-04-09", tz=UTC) == day_interval(
        "2026-04-09", tz=ZoneInfo("UTC")
    )


def test_day_interval_non_utc_shifts_boundaries():
    """The whole point of requiring tz: a user's local day is NOT the UTC
    day. April 9 2026 in Los Angeles is PDT (-07:00), so the day bounds
    must reflect that offset — not UTC."""
    result = day_interval("2026-04-09", tz=ZoneInfo("America/Los_Angeles"))
    assert result == {
        "start_date_time": "2026-04-09T00:00:00-07:00",
        "end_date_time": "2026-04-10T00:00:00-07:00",
    }


def test_day_interval_handles_spring_forward():
    """DST spring-forward day in LA: the day starts in PST (-08:00) and
    ends in PDT (-07:00). The end boundary must be midnight LOCAL TIME of
    the next day."""
    result = day_interval("2026-03-08", tz=ZoneInfo("America/Los_Angeles"))
    assert result == {
        "start_date_time": "2026-03-08T00:00:00-08:00",
        "end_date_time": "2026-03-09T00:00:00-07:00",
    }


def test_day_interval_handles_fall_back():
    """DST fall-back day in LA: the day starts in PDT (-07:00) and ends in
    PST (-08:00). The resulting interval covers 25 real hours (the repeated
    1-2am hour), which is correct — that IS the user's calendar day."""
    result = day_interval("2026-11-01", tz=ZoneInfo("America/Los_Angeles"))
    assert result == {
        "start_date_time": "2026-11-01T00:00:00-07:00",
        "end_date_time": "2026-11-02T00:00:00-08:00",
    }


# --- convert() wraps raw python errors as ConversionError ---


def test_convert_wraps_missing_field_as_conversion_error():
    """Converters should never leak raw KeyError to callers. The public
    contract promises ConversionError for any invalid sample shape."""
    with pytest.raises(ConversionError):
        convert(
            source="oura_raw",
            data_type="heart_rate",
            sample={},  # missing required "bpm" and "timestamp"
        )


def test_convert_wraps_typeerror_as_conversion_error():
    with pytest.raises(ConversionError):
        convert(
            source="oura_raw",
            data_type="heart_rate",
            sample={"bpm": None, "timestamp": "2026-04-09T08:00:00Z"},
        )


# --- convert() tz kwarg is REQUIRED for daily data types ---


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
def test_daily_data_types_require_tz(source, data_type, sample):
    with pytest.raises(ConversionError, match="timezone"):
        convert(source=source, data_type=data_type, sample=sample)


@pytest.mark.parametrize("source,data_type,sample", DAILY_CASES)
def test_daily_data_types_accept_explicit_utc(source, data_type, sample):
    result = convert(source=source, data_type=data_type, sample=sample, tz=UTC)
    interval = result["effective_time_frame"]["time_interval"]
    assert interval["start_date_time"] == "2026-04-09T00:00:00Z"
    assert interval["end_date_time"] == "2026-04-10T00:00:00Z"


@pytest.mark.parametrize("source,data_type,sample", DAILY_CASES)
def test_daily_data_types_respect_non_utc_tz(source, data_type, sample):
    """Proves the tz parameter is actually plumbed through — not just
    validated and ignored."""
    result = convert(
        source=source,
        data_type=data_type,
        sample=sample,
        tz=ZoneInfo("America/Los_Angeles"),
    )
    interval = result["effective_time_frame"]["time_interval"]
    assert interval["start_date_time"] == "2026-04-09T00:00:00-07:00"
    assert interval["end_date_time"] == "2026-04-10T00:00:00-07:00"


# --- timestamp-based data types must reject naive datetimes ---


NAIVE_CASES = [
    (
        "oura_raw",
        "heart_rate",
        {"bpm": 72, "timestamp": "2026-04-09T08:30:00"},
    ),
    (
        "oura_raw",
        "heart_rate_variability",
        {"rmssd": 45.0, "timestamp": "2026-04-09T08:30:00"},
    ),
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
        {
            "bedtime_start": "2026-04-09T22:00:00",
            "bedtime_end": "2026-04-10T06:00:00",
        },
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
        {
            "bedtime_start": "2026-04-09T22:00:00",
            "bedtime_end": "2026-04-10T06:00:00",
        },
    ),
    (
        "ow_normalized",
        "step_count",
        {"timestamp": "2026-04-09T08:30:00", "type": "steps", "value": 10},
    ),
]


@pytest.mark.parametrize("source,data_type,sample", NAIVE_CASES)
def test_timestamp_data_types_reject_naive(source, data_type, sample):
    with pytest.raises(ConversionError, match="timezone"):
        convert(source=source, data_type=data_type, sample=sample)


# --- converters called directly raise ConversionError for domain errors ---


def test_oura_hrv_converter_raises_conversion_error_directly():
    """Calling the converter function directly (bypassing convert() wrapper)
    must still raise ConversionError, not a raw KeyError. The exception
    type is part of the contract, not an implementation detail of the
    wrapper."""
    from omh_shim.sources import oura_raw

    with pytest.raises(ConversionError, match="rmssd"):
        oura_raw.heart_rate_variability(
            {"day": "2026-04-09", "contributors": {"hrv_balance": 70}},
            tz=None,
        )


def test_ow_step_count_converter_raises_conversion_error_directly():
    from omh_shim.sources import ow_normalized

    with pytest.raises(ConversionError):
        ow_normalized.step_count({"foo": "bar"}, tz=UTC)


# --- Schema validation ---


def test_validate_output_passes_for_valid_heart_rate():
    from omh_shim._validate import validate_output

    valid = {
        "heart_rate": {"value": 72, "unit": "beats/min"},
        "effective_time_frame": {"date_time": "2026-04-09T08:00:00Z"},
    }
    validate_output(valid, "omh:heart-rate:2.0")


def test_validate_output_raises_for_invalid_heart_rate():
    from omh_shim._validate import validate_output

    with pytest.raises(ValidationError):
        validate_output({}, "omh:heart-rate:2.0")


def test_validate_output_raises_for_unknown_unit():
    from omh_shim._validate import validate_output

    with pytest.raises(ValidationError):
        validate_output(
            {
                "heart_rate": {"value": 72, "unit": "miles/hour"},
                "effective_time_frame": {"date_time": "2026-04-09T08:00:00Z"},
            },
            "omh:heart-rate:2.0",
        )


def test_schema_ids_is_read_only():
    """SCHEMA_IDS is a MappingProxyType so consumers cannot mutate it and
    silently corrupt the import-time invariant check."""
    import omh_shim

    with pytest.raises(TypeError):
        omh_shim.SCHEMA_IDS["phantom"] = "omh:phantom:1.0"  # type: ignore[index]


def test_registry_not_leaked_at_top_level():
    """REGISTRY is internal plumbing — it must not appear on the public
    top-level package. Consumers needing enumeration use SCHEMA_IDS."""
    import omh_shim

    assert not hasattr(omh_shim, "REGISTRY")


def test_registry_is_read_only():
    """REGISTRY (accessed via _dispatch) is a MappingProxyType so external
    code cannot inject or remove converters at runtime."""
    from omh_shim._dispatch import REGISTRY

    with pytest.raises(TypeError):
        REGISTRY[("x", "y")] = lambda sample, *, tz: {}  # type: ignore[index]


def test_hrv_schema_is_local_not_omh_namespace():
    """The HRV schema is a placeholder — OMH has not published a canonical
    HRV schema. It must live under the ``local:`` namespace to avoid
    implying OMH-standard interoperability."""
    from omh_shim import SCHEMA_IDS

    assert SCHEMA_IDS["heart_rate_variability"].startswith("local:")
    assert not SCHEMA_IDS["heart_rate_variability"].startswith("omh:")


def test_all_top_level_schemas_load():
    from omh_shim import SCHEMA_IDS
    from omh_shim._schema_loader import load

    for schema_id in SCHEMA_IDS.values():
        assert isinstance(load(schema_id), dict), f"failed to load {schema_id}"


# --- numeric precision ---


def test_oura_heart_rate_preserves_fractional_bpm():
    """Oura may report fractional bpm; converters must not silently round
    away precision. Downstream consumers can round themselves if needed."""
    result = convert(
        source="oura_raw",
        data_type="heart_rate",
        sample={"bpm": 72.456, "timestamp": "2026-04-09T08:00:00Z"},
    )
    assert result["heart_rate"]["value"] == 72.456


def test_ow_sleep_duration_preserves_fractional_minutes():
    """Fractional minutes must round-trip through the minutes-to-seconds
    scaling without truncation. 32.5 minutes == 1950 seconds (not 1920)."""
    result = convert(
        source="ow_normalized",
        data_type="sleep_duration",
        sample={"date": "2026-04-09", "sleep_total_duration_minutes": 32.5},
        tz=UTC,
    )
    assert result["sleep_duration"]["value"] == 1950


# --- validate kwarg ---


def test_convert_validate_false_skips_validation(monkeypatch):
    """``validate=False`` must not call the validator at all. If validation
    is expensive or a consumer deliberately wants to produce a draft record
    without enforcing conformance, the opt-out must actually opt out.

    We patch ``omh_shim._validate.validate_output`` at the source module
    (not a re-exported local binding), so the test is robust to refactors
    of how ``convert()`` internally references the validator.
    """
    from omh_shim import _validate

    def explode(*args, **kwargs):
        raise AssertionError("validate_output must not be called when validate=False")

    monkeypatch.setattr(_validate, "validate_output", explode)

    result = convert(
        source="ow_normalized",
        data_type="heart_rate",
        sample={
            "timestamp": "2026-04-09T08:00:00Z",
            "type": "heart_rate",
            "value": 72,
        },
        validate=False,
    )
    assert result["heart_rate"] == {"value": 72, "unit": "beats/min"}


def test_convert_validate_true_calls_validator(monkeypatch):
    """The flipside: validate=True (default) must call validate_output with
    the right schema id, so we know the opt-out is actually wired up."""
    from omh_shim import _validate

    calls = []
    monkeypatch.setattr(
        _validate,
        "validate_output",
        lambda output, schema_id: calls.append(schema_id),
    )

    convert(
        source="ow_normalized",
        data_type="heart_rate",
        sample={
            "timestamp": "2026-04-09T08:00:00Z",
            "type": "heart_rate",
            "value": 72,
        },
    )
    assert calls == ["omh:heart-rate:2.0"]
