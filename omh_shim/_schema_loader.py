"""Load vendored OMH JSON schemas by schema id.

Schema ids look like ``omh:heart-rate:2.0`` or ``local:heart-rate-variability:1.0``.
Filenames are maintained in an explicit lookup table rather than derived via
string substitution: a derived scheme like ``:`` → ``_`` and ``.`` → ``-``
has a latent collision (``omh:a.b:1.0`` and ``omh:a-b:1.0`` would map to the
same file), and a single source of truth is easier to audit.
"""

import importlib.resources
import json
from functools import cache
from typing import Any

# Explicit schema_id -> filename (no string munging).
_FILENAMES: dict[str, str] = {
    "omh:heart-rate:2.0": "omh_heart-rate_2-0.json",
    "local:heart-rate-variability:1.0": "local_heart-rate-variability_1-0.json",
    "omh:step-count:3.0": "omh_step-count_3-0.json",
    "omh:sleep-duration:2.0": "omh_sleep-duration_2-0.json",
    "omh:sleep-episode:1.1": "omh_sleep-episode_1-1.json",
    "omh:physical-activity:1.2": "omh_physical-activity_1-2.json",
}


def known_ids() -> frozenset[str]:
    """The set of schema ids this loader knows how to locate on disk."""
    return frozenset(_FILENAMES.keys())


@cache
def load(schema_id: str) -> dict[str, Any]:
    """Load the vendored JSON schema with the given schema id.

    Raises
    ------
    KeyError
        If ``schema_id`` is not in the known filename table.
    FileNotFoundError
        If the table points at a missing file (should never happen in a
        correctly-packaged build).
    """
    try:
        filename = _FILENAMES[schema_id]
    except KeyError as e:
        raise KeyError(
            f"unknown schema id {schema_id!r} — add it to _FILENAMES in "
            "omh_shim/_schema_loader.py and vendor the corresponding file "
            "under omh_shim/schemas/"
        ) from e
    resource = importlib.resources.files("omh_shim.schemas").joinpath(filename)
    if not resource.is_file():
        raise FileNotFoundError(
            f"vendored schema file missing: {filename} (referenced by {schema_id!r})"
        )
    with resource.open("r", encoding="utf-8") as f:
        loaded: dict[str, Any] = json.load(f)
    return loaded
