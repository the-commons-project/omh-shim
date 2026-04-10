"""(source, data_type) -> converter function lookup."""

from collections.abc import Mapping
from datetime import tzinfo
from types import MappingProxyType
from typing import Any, Protocol

from omh_shim.errors import ConversionError
from omh_shim.sources import oura_raw, ow_normalized


class _Converter(Protocol):
    """Every converter takes a read-only sample mapping and a keyword-only
    timezone, returning a fresh dict-shaped record conforming to its target
    schema. Daily converters require a non-None ``tz``; timestamp-based
    converters accept ``None`` but must still receive the kwarg.

    The uniform signature is deliberate. An alternative design with two
    protocols (one daily, one timestamp) would force ``convert()`` to branch
    on ``data_type`` at dispatch time — more code, more tests, no benefit
    for the caller. Runtime rejection of ``tz=None`` for daily types (via
    ``day_interval``) is the simpler correct behavior.
    """

    def __call__(
        self, sample: Mapping[str, Any], *, tz: tzinfo | None
    ) -> dict[str, Any]: ...


_REGISTRY_SOURCE: dict[tuple[str, str], _Converter] = {
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

# Public view is a read-only proxy so consumers can enumerate the registry
# without being able to mutate it.
REGISTRY: Mapping[tuple[str, str], _Converter] = MappingProxyType(_REGISTRY_SOURCE)


def lookup(source: str, data_type: str) -> _Converter:
    """Return the registered converter, or raise ``ConversionError``."""
    try:
        return REGISTRY[(source, data_type)]
    except KeyError as e:
        raise ConversionError(
            f"No converter for source={source!r} data_type={data_type!r}"
        ) from e
