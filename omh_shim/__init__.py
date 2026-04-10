"""omh-shim: convert wearable health data to Open mHealth schemas."""

from collections.abc import Mapping
from datetime import tzinfo
from types import MappingProxyType
from typing import Any

from omh_shim import _dispatch, _schema_loader, _validate
from omh_shim._helpers import build_header
from omh_shim.errors import ConversionError, ValidationError

__all__ = ["convert", "ConversionError", "ValidationError", "SCHEMA_IDS"]
__version__ = "0.1.0"

SCHEMA_IDS: Mapping[str, str] = MappingProxyType({
    "heart_rate": "omh:heart-rate:2.0",
    "heart_rate_variability": "local:heart-rate-variability:1.0",
    "step_count": "omh:step-count:3.0",
    "sleep_duration": "omh:sleep-duration:2.0",
    "sleep_episode": "omh:sleep-episode:1.1",
    "physical_activity": "omh:physical-activity:1.2",
    "oxygen_saturation": "omh:oxygen-saturation:2.0",
})
"""Read-only mapping of data_type -> schema id. ``heart_rate_variability``
uses a ``local:`` namespace placeholder (OMH has no canonical HRV schema)."""

# Fail fast if someone adds a converter without a schema id (or vice versa),
# or a schema id without a loader filename entry. Uses raise (not assert)
# so it survives python -O.
_registered = {dt for (_, dt) in _dispatch.REGISTRY}
if _registered != SCHEMA_IDS.keys():
    raise RuntimeError(f"REGISTRY/SCHEMA_IDS drift: {_registered ^ SCHEMA_IDS.keys()}")
if set(SCHEMA_IDS.values()) != _schema_loader.known_ids():
    raise RuntimeError(
        f"SCHEMA_IDS/loader drift: {set(SCHEMA_IDS.values()) ^ _schema_loader.known_ids()}"
    )
del _registered


def _extract_datasheets(sample: Mapping[str, Any]) -> list[dict[str, str]] | None:
    """Extract external_datasheets from the sample's source metadata.

    OW samples include ``source.provider`` and ``source.device``. Oura raw
    samples don't have a source field — the provider is implicit.
    """
    source_meta = sample.get("source") if isinstance(sample, Mapping) else None
    if not source_meta or not isinstance(source_meta, Mapping):
        return None
    device = source_meta.get("device") or source_meta.get("device_model")
    provider = source_meta.get("provider") or source_meta.get("source_name")
    ref = device or provider
    if not ref:
        return None
    return [{"datasheet_type": "manufacturer", "datasheet_reference": str(ref)}]


def convert(
    source: str,
    data_type: str,
    sample: Mapping[str, Any],
    *,
    tz: tzinfo | None = None,
    validate: bool = True,
) -> dict[str, Any]:
    """Convert one source sample to one Open mHealth data-point.

    Always returns the full IEEE 1752.1 data-point envelope::

        {"header": {...}, "body": {...}}

    The header includes ``uuid``, ``schema_id``, ``source_creation_date_time``,
    ``modality``, and ``external_datasheets`` (auto-populated from the sample's
    source metadata when available).

    ``tz`` is required for daily data types (step_count, physical_activity,
    sleep_duration) — pass ``datetime.UTC`` or a ``ZoneInfo``.

    Raises ``ConversionError`` on invalid input, ``ValidationError`` on
    schema mismatch (when ``validate=True``).
    """
    converter = _dispatch.lookup(source, data_type)
    try:
        body = converter(sample, tz=tz)
    except (KeyError, ValueError, TypeError) as e:
        raise ConversionError(
            f"{source}/{data_type}: {type(e).__name__}: {e}"
        ) from e
    schema_id = SCHEMA_IDS[data_type]
    if validate:
        _validate.validate_output(body, schema_id)
    return {
        "header": build_header(
            schema_id,
            external_datasheets=_extract_datasheets(sample),
        ),
        "body": body,
    }
