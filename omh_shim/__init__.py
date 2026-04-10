"""omh-shim: convert wearable health data to Open mHealth schemas.

Public API:
    convert(source, data_type, sample, *, tz=None, validate=True) -> dict
    ConversionError
    ValidationError
    SCHEMA_IDS  (mapping of data_type -> schema id)
"""

from datetime import tzinfo

from omh_shim._dispatch import REGISTRY, lookup
from omh_shim._validate import validate_output
from omh_shim.errors import ConversionError, ValidationError

__all__ = ["convert", "ConversionError", "ValidationError", "SCHEMA_IDS"]
__version__ = "0.1.0"

# data_type -> schema id for output validation.
# Note: heart_rate_variability uses a local placeholder schema because Open
# mHealth has not published a canonical HRV schema. It lives under the
# ``local:`` namespace to avoid implying OMH-standard interoperability.
SCHEMA_IDS: dict[str, str] = {
    "heart_rate": "omh:heart-rate:2.0",
    "heart_rate_variability": "local:heart-rate-variability:1.0",
    "step_count": "omh:step-count:3.0",
    "sleep_duration": "omh:sleep-duration:2.0",
    "sleep_episode": "omh:sleep-episode:1.1",
    "physical_activity": "omh:physical-activity:1.2",
}

# Import-time invariant: every registered converter must have a schema id,
# and every declared schema id must have at least one converter. Catches
# drift between REGISTRY and SCHEMA_IDS at import. Uses an explicit raise
# (not ``assert``) so the check survives ``python -O`` / PYTHONOPTIMIZE.
_registered_types = {data_type for (_, data_type) in REGISTRY}
_missing_schema_ids = _registered_types - SCHEMA_IDS.keys()
_missing_converters = SCHEMA_IDS.keys() - _registered_types
if _missing_schema_ids or _missing_converters:
    raise RuntimeError(
        "REGISTRY and SCHEMA_IDS are out of sync: "
        f"in REGISTRY but missing schema id: {sorted(_missing_schema_ids)}; "
        f"in SCHEMA_IDS but missing converter: {sorted(_missing_converters)}"
    )
del _registered_types, _missing_schema_ids, _missing_converters


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
        output = converter(sample, tz=tz)
    except (KeyError, ValueError, TypeError) as e:
        raise ConversionError(
            f"{source}/{data_type} could not convert sample: "
            f"{type(e).__name__}: {e}"
        ) from e
    if validate:
        validate_output(output, SCHEMA_IDS[data_type])
    return output
