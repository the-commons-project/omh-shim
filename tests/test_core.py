"""Smoke + unit tests for the core primitives.

Schema-validation tests are written here too but skipped until Task 3
(schema vendoring) lands. Un-skip them once the schemas are in place.
"""

import pytest

from omh_shim import ConversionError, ValidationError, convert
from omh_shim._dispatch import _REGISTRY, lookup, register


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


def test_register_then_lookup_roundtrip():
    @register(source="test_src", data_type="test_dt")
    def _converter(sample):
        return {"echoed": sample}

    try:
        fn = lookup("test_src", "test_dt")
        assert fn({"x": 1}) == {"echoed": {"x": 1}}
    finally:
        _REGISTRY.pop(("test_src", "test_dt"), None)


def test_convert_propagates_unknown_pair_as_conversion_error():
    with pytest.raises(ConversionError):
        convert(source="ow_normalized", data_type="not_a_real_type", sample={})


# --- Schema validation tests (un-skip after Task 3) ---


@pytest.mark.skip(reason="Schemas not yet vendored — un-skip after Task 3")
def test_validate_output_passes_for_valid_heart_rate():
    from omh_shim._validate import validate_output

    valid = {
        "header": {
            "id": "abc-123",
            "creation_date_time": "2026-04-09T08:00:00Z",
            "schema_id": {"namespace": "omh", "name": "heart-rate", "version": "2.0"},
        },
        "body": {
            "heart_rate": {"value": 72, "unit": "beats/min"},
            "effective_time_frame": {"date_time": "2026-04-09T08:00:00Z"},
        },
    }
    validate_output(valid, "omh:heart-rate:2.0")


@pytest.mark.skip(reason="Schemas not yet vendored — un-skip after Task 3")
def test_validate_output_raises_for_invalid_heart_rate():
    from omh_shim._validate import validate_output

    with pytest.raises(ValidationError):
        validate_output({}, "omh:heart-rate:2.0")
