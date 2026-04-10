"""omh-shim: convert wearable health data to Open mHealth schemas.

Public API:
    convert(source, data_type, sample, *, validate=True) -> dict
    ConversionError
    ValidationError
"""

from omh_shim._dispatch import lookup
from omh_shim._validate import validate_output
from omh_shim.errors import ConversionError, ValidationError

__all__ = ["convert", "ConversionError", "ValidationError"]
__version__ = "0.1.0.dev0"

# Public data_type names map to OMH schema ids for output validation.
_OMH_SCHEMA_ID: dict[str, str] = {
    "heart_rate": "omh:heart-rate:2.0",
    "heart_rate_variability": "omh:heart-rate-variability:1.0",
    "step_count": "omh:step-count:3.0",
    "sleep_duration": "omh:sleep-duration:2.0",
    "sleep_episode": "omh:sleep-episode:1.1",
    "physical_activity": "omh:physical-activity:2.0",
}


def convert(
    source: str,
    data_type: str,
    sample: dict,
    *,
    validate: bool = True,
) -> dict:
    """Convert one source sample to one Open mHealth record.

    Parameters
    ----------
    source:
        Registered source key, e.g. ``"ow_normalized"`` or ``"oura_raw"``.
    data_type:
        Target OMH schema name, e.g. ``"heart_rate"`` or ``"sleep_episode"``.
    sample:
        Source-specific input dict. Shape depends on ``source`` and
        ``data_type``; see the relevant converter's docstring.
    validate:
        Keyword-only. If True (default), validate the output against the
        target OMH schema and raise ``ValidationError`` on mismatch.

    Returns
    -------
    dict
        An Open mHealth record conforming to the target schema.

    Raises
    ------
    ConversionError
        No converter registered, or sample shape is invalid.
    ValidationError
        Output failed OMH schema validation (only when ``validate=True``).
    """
    output = lookup(source, data_type)(sample)
    if validate:
        validate_output(output, _OMH_SCHEMA_ID[data_type])
    return output


# Source packages register themselves on import.
import omh_shim.sources.ow_normalized  # noqa: E402, F401
import omh_shim.sources.oura_raw  # noqa: E402, F401
