"""omh-shim: convert wearable health data to Open mHealth schemas.

Public API:
    convert(source, data_type, sample, *, tz=None, validate=True) -> dict
    ConversionError
    ValidationError
"""

from datetime import tzinfo

from omh_shim._dispatch import REGISTRY, lookup
from omh_shim._validate import validate_output
from omh_shim.errors import ConversionError, ValidationError

__all__ = ["convert", "ConversionError", "ValidationError"]
__version__ = "0.1.0"

# data_type -> schema id for output validation.
# Note: heart_rate_variability uses a local placeholder schema because Open
# mHealth has not published a canonical HRV schema. It lives under the
# ``local:`` namespace to avoid implying OMH-standard interoperability.
_SCHEMA_ID: dict[str, str] = {
    "heart_rate": "omh:heart-rate:2.0",
    "heart_rate_variability": "local:heart-rate-variability:1.0",
    "step_count": "omh:step-count:3.0",
    "sleep_duration": "omh:sleep-duration:2.0",
    "sleep_episode": "omh:sleep-episode:1.1",
    "physical_activity": "omh:physical-activity:1.2",
}

# Import-time invariant: every registered converter must have a schema id,
# and every declared schema id must have at least one converter. Catches
# drift between REGISTRY and _SCHEMA_ID the moment the package imports.
assert {data_type for (_, data_type) in REGISTRY} == _SCHEMA_ID.keys(), (
    "REGISTRY and _SCHEMA_ID are out of sync — every (source, data_type) in "
    "REGISTRY must have a matching entry in _SCHEMA_ID and vice versa"
)


def convert(
    source: str,
    data_type: str,
    sample: dict,
    *,
    tz: tzinfo | None = None,
    validate: bool = True,
) -> dict:
    """Convert one source sample to one Open mHealth record.

    Parameters
    ----------
    source:
        Registered source key, e.g. ``"ow_normalized"`` or ``"oura_raw"``.
    data_type:
        Target schema name, e.g. ``"heart_rate"`` or ``"sleep_episode"``.
    sample:
        Source-specific input dict. Shape depends on ``source`` and
        ``data_type``; see the relevant converter's docstring.
    tz:
        Keyword-only. Timezone to interpret ``day``/``date`` fields in for
        daily data types (``step_count``, ``physical_activity``,
        ``sleep_duration``). REQUIRED for those types; pass ``datetime.UTC``
        explicitly when the upstream data is UTC-anchored, or a ``ZoneInfo``
        for the user's local timezone. Ignored by timestamp-based data types.
    validate:
        Keyword-only. If True (default), validate the output against the
        target schema and raise ``ValidationError`` on mismatch.

    Returns
    -------
    dict
        A record conforming to the target schema.

    Raises
    ------
    ConversionError
        No converter registered, sample shape is invalid, datetimes are
        naive, or a required timezone is missing.
    ValidationError
        Output failed schema validation (only when ``validate=True``).
    """
    converter = lookup(source, data_type)
    try:
        output = converter(sample, tz)
    except (KeyError, ValueError, TypeError) as e:
        raise ConversionError(
            f"{source}/{data_type} could not convert sample: {e}"
        ) from e
    if validate:
        validate_output(output, _SCHEMA_ID[data_type])
    return output
