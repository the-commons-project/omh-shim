"""Load vendored OMH JSON schemas by schema id.

Schema ids look like ``omh:heart-rate:2.0``. The on-disk filename is derived
from the id by replacing ``:`` with ``_`` and ``.`` with ``-``, then appending
``.json`` (e.g. ``omh:heart-rate:2.0`` -> ``omh_heart-rate_2-0.json``).
"""

import importlib.resources
import json
from functools import cache


def _id_to_filename(schema_id: str) -> str:
    return schema_id.replace(":", "_").replace(".", "-") + ".json"


@cache
def load(schema_id: str) -> dict:
    """Load the vendored JSON schema with the given OMH id.

    Raises
    ------
    FileNotFoundError
        If no vendored file matches the id.
    """
    filename = _id_to_filename(schema_id)
    resource = importlib.resources.files("omh_shim.schemas").joinpath(filename)
    if not resource.is_file():
        raise FileNotFoundError(f"No vendored schema for id={schema_id!r} (expected {filename})")
    with resource.open("r", encoding="utf-8") as f:
        return json.load(f)
