"""omh-shim: convert wearable health data to Open mHealth schemas.

Public API:
    convert(source, data_type, sample, *, tz=None, validate=True) -> dict
    ConversionError
    ValidationError
    SCHEMA_IDS  (read-only mapping of data_type -> schema id)
"""

from collections.abc import Mapping
from datetime import tzinfo
from types import MappingProxyType
from typing import Any

from omh_shim import _dispatch, _schema_loader, _validate
from omh_shim.errors import ConversionError, ValidationError

__all__ = ["convert", "ConversionError", "ValidationError", "SCHEMA_IDS"]
__version__ = "0.1.0"

# data_type -> schema id for output validation.
# Note: heart_rate_variability uses a local placeholder schema because Open
# mHealth has not published a canonical HRV schema. It lives under the
# ``local:`` namespace to avoid implying OMH-standard interoperability.
_SCHEMA_IDS_SOURCE: dict[str, str] = {
    "heart_rate": "omh:heart-rate:2.0",
    "heart_rate_variability": "local:heart-rate-variability:1.0",
    "step_count": "omh:step-count:3.0",
    "sleep_duration": "omh:sleep-duration:2.0",
    "sleep_episode": "omh:sleep-episode:1.1",
    "physical_activity": "omh:physical-activity:1.2",
}

#: Public read-only mapping of ``data_type`` -> schema id. Wrapped in
#: ``MappingProxyType`` so consumers cannot mutate it and corrupt the
#: import-time registry invariant.
SCHEMA_IDS: Mapping[str, str] = MappingProxyType(_SCHEMA_IDS_SOURCE)

# Import-time invariants:
#
# 1. Every registered converter has a schema id, and every declared schema
#    id has at least one converter.
# 2. Every schema id has an explicit filename entry in the loader.
#
# Uses explicit ``raise`` (not ``assert``) so the checks survive
# ``python -O`` / PYTHONOPTIMIZE, which strips asserts.
_registered_types = {data_type for (_, data_type) in _dispatch.REGISTRY}
_missing_schema_ids = _registered_types - SCHEMA_IDS.keys()
_missing_converters = SCHEMA_IDS.keys() - _registered_types
if _missing_schema_ids or _missing_converters:
    raise RuntimeError(
        "REGISTRY and SCHEMA_IDS are out of sync: "
        f"in REGISTRY but missing schema id: {sorted(_missing_schema_ids)}; "
        f"in SCHEMA_IDS but missing converter: {sorted(_missing_converters)}"
    )

_loader_known = _schema_loader.known_ids()
_schema_ids_without_files = set(SCHEMA_IDS.values()) - _loader_known
_files_without_schema_ids = _loader_known - set(SCHEMA_IDS.values())
if _schema_ids_without_files or _files_without_schema_ids:
    raise RuntimeError(
        "SCHEMA_IDS and _schema_loader filename table are out of sync: "
        f"in SCHEMA_IDS but no filename: {sorted(_schema_ids_without_files)}; "
        f"in loader but no schema id: {sorted(_files_without_schema_ids)}"
    )

del _registered_types, _missing_schema_ids, _missing_converters
del _loader_known, _schema_ids_without_files, _files_without_schema_ids


def convert(
    source: str,
    data_type: str,
    sample: dict[str, Any],
    *,
    tz: tzinfo | None = None,
    validate: bool = True,
) -> dict[str, Any]:
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
    converter = _dispatch.lookup(source, data_type)
    try:
        output = converter(sample, tz=tz)
    except (KeyError, ValueError, TypeError) as e:
        raise ConversionError(
            f"{source}/{data_type} could not convert sample: "
            f"{type(e).__name__}: {e}"
        ) from e
    if validate:
        # Called via the module attribute (not a re-exported local binding)
        # so tests can monkeypatch ``omh_shim._validate.validate_output`` at
        # a single stable location.
        _validate.validate_output(output, SCHEMA_IDS[data_type])
    return output
