"""Internal dispatch registry for (source, data_type) -> converter functions."""

from collections.abc import Callable

from omh_shim.errors import ConversionError

_Converter = Callable[[dict], dict]
_REGISTRY: dict[tuple[str, str], _Converter] = {}


def register(*, source: str, data_type: str) -> Callable[[_Converter], _Converter]:
    """Decorator that registers a converter under ``(source, data_type)``."""

    def _wrap(fn: _Converter) -> _Converter:
        _REGISTRY[(source, data_type)] = fn
        return fn

    return _wrap


def lookup(source: str, data_type: str) -> _Converter:
    """Return the registered converter, or raise ``ConversionError``."""
    try:
        return _REGISTRY[(source, data_type)]
    except KeyError as e:
        raise ConversionError(
            f"No converter for source={source!r} data_type={data_type!r}"
        ) from e
