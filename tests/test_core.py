"""Smoke + unit tests for the core primitives.

Schema-validation tests are written here too but skipped until Task 3
(schema vendoring) lands. Un-skip them once the schemas are in place.
"""

import pytest

from omh_shim import ConversionError, ValidationError, convert
from omh_shim._dispatch import lookup


def test_package_imports_and_exports_public_api():
    assert callable(convert)
    assert issubclass(ConversionError, Exception)
    assert issubclass(ValidationError, Exception)


def test_lookup_unknown_pair_raises_conversion_error():
    with pytest.raises(ConversionError) as exc_info:
        lookup("nope_source", "nope_data_type")
    msg = str(exc_info.value)
    assert "nope_source" in msg
    assert "nope_data_type" in msg


def test_convert_propagates_unknown_pair_as_conversion_error():
    with pytest.raises(ConversionError):
        convert(source="ow_normalized", data_type="not_a_real_type", sample={})


# --- Schema validation tests ---


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


def test_all_six_top_level_schemas_load():
    from omh_shim._schema_loader import load

    for schema_id in [
        "omh:heart-rate:2.0",
        "omh:heart-rate-variability:1.0",
        "omh:step-count:3.0",
        "omh:sleep-duration:2.0",
        "omh:sleep-episode:1.1",
        "omh:physical-activity:1.2",
    ]:
        schema = load(schema_id)
        assert isinstance(schema, dict), f"failed to load {schema_id}"
