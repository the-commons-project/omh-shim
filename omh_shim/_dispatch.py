"""(source, data_type) -> converter function lookup."""

from collections.abc import Callable

from omh_shim.errors import ConversionError
from omh_shim.sources import oura_raw, ow_normalized

_Converter = Callable[[dict], dict]

REGISTRY: dict[tuple[str, str], _Converter] = {
    ("oura_raw", "heart_rate"):              oura_raw.heart_rate,
    ("oura_raw", "heart_rate_variability"):  oura_raw.heart_rate_variability,
    ("oura_raw", "step_count"):              oura_raw.step_count,
    ("oura_raw", "sleep_duration"):          oura_raw.sleep_duration,
    ("oura_raw", "sleep_episode"):           oura_raw.sleep_episode,
    ("oura_raw", "physical_activity"):       oura_raw.physical_activity,
    ("ow_normalized", "heart_rate"):             ow_normalized.heart_rate,
    ("ow_normalized", "heart_rate_variability"): ow_normalized.heart_rate_variability,
    ("ow_normalized", "step_count"):             ow_normalized.step_count,
    ("ow_normalized", "sleep_duration"):         ow_normalized.sleep_duration,
    ("ow_normalized", "sleep_episode"):          ow_normalized.sleep_episode,
    ("ow_normalized", "physical_activity"):      ow_normalized.physical_activity,
}


def lookup(source: str, data_type: str) -> _Converter:
    """Return the registered converter, or raise ``ConversionError``."""
    try:
        return REGISTRY[(source, data_type)]
    except KeyError as e:
        raise ConversionError(
            f"No converter for source={source!r} data_type={data_type!r}"
        ) from e
