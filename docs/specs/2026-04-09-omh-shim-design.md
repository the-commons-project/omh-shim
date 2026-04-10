# omh-shim v0.1 Design

**Date:** 2026-04-09
**Status:** Draft for review
**Owner:** JupyterHealth Exchange (JHE) team
**Repo:** `omh-shim` (JHE-owned, to be rewritten from the existing `omh_shim` PoC repo)
**License:** MIT

---

## Summary

`omh-shim` is a JHE-owned Python library that converts wearable health data from a variety of source schemas into [Open mHealth](https://www.openmhealth.org/) schemas. Its single responsibility is schema conversion: source-specific JSON in, OMH-conformant JSON out. It has no FHIR knowledge, no HTTP client, no database, and no JHE-specific dependencies — any Python application targeting Open mHealth can use it.

v0.1 ships 12 converter functions covering 6 OMH data types across 2 input sources:

- **`ow_normalized`** — Open Wearables' normalized read-API response shapes (the `TimeSeriesSample`, `ActivitySummary`, `Workout`, etc. types under `backend/app/schemas/responses/activity/`)
- **`oura_raw`** — Oura Ring's v2 API response shapes, ported with permission from [dicristea/oura-clinical-workbench](https://github.com/dicristea/oura-clinical-workbench) with attribution

The library is extensible by dropping a new source directory under `omh_shim/sources/` and registering converters in the dispatch table. A future v0.2 will add Garmin, Fitbit, and Apple Health sources, plus additional OMH target data types.

## Goals

1. **Pure function library.** `convert(source, data_type, sample) -> dict`. No I/O beyond reading vendored schema files at import time.
2. **Multi-source from day one.** The architecture supports adding new input schemas without touching the core dispatch — just drop a new source directory.
3. **Output correctness by default.** Every conversion output is validated against the target OMH JSON schema before being returned. Optional opt-out for performance-critical callers.
4. **Zero JHE coupling.** The library must be usable by any Python project that wants to produce Open mHealth data. No imports from `core.*`, no Django, no FHIR.
5. **Credit where credit is due.** The `oura_raw` source ports mapping logic from `dicristea/oura-clinical-workbench` with full attribution in source file headers, an `AUTHORS.md` file, and a README credit.

## Non-goals

These are things the library deliberately does *not* do in v0.1. They may be reconsidered in future versions but are explicitly out of scope today:

- **No HTTP client.** The library does not fetch data from Oura's API, OW's API, or anywhere else. Callers pull data, then hand dicts to `convert()`.
- **No database / storage.** The library is stateless between calls.
- **No async.** `convert()` is a synchronous function. For callers that need concurrency, `concurrent.futures.ThreadPoolExecutor` or equivalent works fine since the function is pure and cheap.
- **No streaming conversion.** One sample per call. Bulk conversion is a caller-side list comprehension.
- **No FHIR building.** Wrapping an OMH record in a FHIR Observation is JHE's job (`core/services/ow_ingest/omh_to_fhir.py`, specified separately).
- **No persistence of dispatch state.** The registry is built at import time from module imports, not from a config file or database.
- **No custom schema validation beyond OMH.** If a caller wants stricter validation, they can wrap the library.
- **No dedup logic.** If the same sample is converted twice, two identical outputs are returned. Dedup is the caller's responsibility.

## Architecture

### Package layout

```
omh-shim/
├── pyproject.toml                       # PEP 621 metadata, Python 3.11+ support
├── README.md
├── AUTHORS.md                           # credit to dicristea upstream for oura_raw
├── LICENSE                              # MIT
├── CHANGELOG.md
├── .github/
│   └── workflows/
│       └── test.yml                     # GitHub Actions: pytest on 3.11, 3.12
├── omh_shim/
│   ├── __init__.py                      # public API: convert, ConversionError, ValidationError
│   ├── _dispatch.py                     # registry: (source, data_type) -> callable
│   ├── _schema_loader.py                # importlib.resources-based OMH schema loader + cache
│   ├── _validate.py                     # jsonschema-based output validator
│   ├── errors.py                        # ConversionError, ValidationError definitions
│   ├── schemas/                         # vendored OMH JSON schemas
│   │   ├── README.md                    # notes the upstream commit SHA
│   │   ├── omh_heart-rate_2-0.json
│   │   ├── omh_heart-rate-variability_1-0.json  (or IEEE equivalent; see §Implementation flag)
│   │   ├── omh_step-count_3-0.json
│   │   ├── omh_sleep-duration_2-0.json
│   │   ├── omh_sleep-episode_1-1.json
│   │   └── omh_physical-activity_2-0.json
│   └── sources/
│       ├── __init__.py
│       ├── ow_normalized/
│       │   ├── __init__.py              # imports each converter to populate registry
│       │   ├── heart_rate.py
│       │   ├── heart_rate_variability.py
│       │   ├── step_count.py
│       │   ├── sleep_duration.py
│       │   ├── sleep_episode.py
│       │   └── physical_activity.py
│       └── oura_raw/
│           ├── __init__.py
│           ├── heart_rate.py            # ported from dicristea
│           ├── heart_rate_variability.py
│           ├── step_count.py
│           ├── sleep_duration.py
│           ├── sleep_episode.py
│           └── physical_activity.py
└── tests/
    ├── __init__.py
    ├── fixtures/
    │   ├── ow_normalized/
    │   │   ├── heart_rate_input.json
    │   │   ├── heart_rate_expected.json
    │   │   ├── ... (one input/expected pair per converter, minimum)
    │   └── oura_raw/
    │       └── ... (same structure)
    ├── test_dispatch.py
    ├── test_schema_loader.py
    ├── test_validate.py
    ├── test_ow_normalized.py            # parameterized over all fixtures
    └── test_oura_raw.py                 # parameterized over all fixtures
```

### Public API

Only four symbols are exported from `omh_shim`:

```python
from omh_shim import convert, ConversionError, ValidationError

# Full signature:
#   def convert(source: str, data_type: str, sample: dict, *, validate: bool = True) -> dict
#
# `validate` is keyword-only. Positional args are (source, data_type, sample).

omh_record: dict = convert(
    source="ow_normalized",       # or "oura_raw"
    data_type="heart_rate",       # one of the 6 v0.1 target schemas
    sample=source_dict,           # source-specific input shape
    validate=True,                # keyword-only; default is True
)
```

`convert()` raises:

- **`ConversionError`** — unknown `(source, data_type)` pair; source sample is missing required fields; source sample shape does not match what the converter expects.
- **`ValidationError`** — conversion produced output that does not validate against the target OMH schema (only raised if `validate=True`, which is the default).

Every other symbol in the package is private (single-underscore prefix at the module level, or not exported from `__init__.py`).

### Dispatch mechanism

`_dispatch.py` maintains a module-level dict:

```python
# omh_shim/_dispatch.py
from typing import Callable

_REGISTRY: dict[tuple[str, str], Callable[[dict], dict]] = {}


def register(source: str, data_type: str):
    """Decorator used by each converter module to register itself."""
    def _wrap(fn):
        _REGISTRY[(source, data_type)] = fn
        return fn
    return _wrap


def lookup(source: str, data_type: str) -> Callable[[dict], dict]:
    try:
        return _REGISTRY[(source, data_type)]
    except KeyError:
        raise ConversionError(
            f"No converter registered for source={source!r} data_type={data_type!r}"
        )
```

Each converter module uses the decorator:

```python
# omh_shim/sources/ow_normalized/heart_rate.py
from omh_shim._dispatch import register


@register(source="ow_normalized", data_type="heart_rate")
def convert(sample: dict) -> dict:
    """Convert an OW TimeSeriesSample of type=heart_rate to omh:heart-rate:2.0."""
    # ... pure mapping code, no I/O ...
    return {
        "header": {...},
        "body": {...},
    }
```

Registration happens at **import time**. The `omh_shim/sources/ow_normalized/__init__.py` imports every converter module in the package, which triggers the `@register` decorators and populates the registry. Same for `oura_raw/__init__.py`. The top-level `omh_shim/__init__.py` imports both source packages so the registry is fully populated after `import omh_shim`.

**Alternative considered and rejected:** a hand-maintained dispatch dict in `_dispatch.py` listing every converter by module path. Rejected because the decorator pattern scales better as sources are added and puts the registration right next to the converter function, which is where a new contributor would look.

### Schema loading and validation

OMH JSON schemas are vendored into `omh_shim/schemas/`, copied from [openmhealth/schemas](https://github.com/openmhealth/schemas) at a specific commit SHA recorded in `omh_shim/schemas/README.md`. They are loaded at import time via `importlib.resources`:

```python
# omh_shim/_schema_loader.py
import json
import importlib.resources
from functools import lru_cache


@lru_cache(maxsize=None)
def load(schema_id: str) -> dict:
    """Load an OMH JSON schema by its id (e.g. 'omh:heart-rate:2.0')."""
    filename = schema_id.replace(":", "_").replace(".", "-") + ".json"
    with importlib.resources.files("omh_shim.schemas").joinpath(filename).open() as f:
        return json.load(f)
```

`_validate.py` uses the standard `jsonschema` library to validate an output against its target schema:

```python
# omh_shim/_validate.py
from jsonschema import Draft7Validator
from omh_shim.errors import ValidationError
from omh_shim._schema_loader import load as load_schema


def validate_output(output: dict, schema_id: str) -> None:
    schema = load_schema(schema_id)
    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(output), key=lambda e: e.path)
    if errors:
        raise ValidationError(
            f"Output does not conform to {schema_id}: "
            + "; ".join(f"{list(e.path)}: {e.message}" for e in errors)
        )
```

### Refreshing vendored schemas

A `tools/refresh_schemas.py` script pulls fresh copies of the relevant schemas from `openmhealth/schemas` at HEAD, diffs them against the current vendored copies, and prints the diff for manual review before committing. Intended to run maybe once a year when Open mHealth publishes a new version.

```
$ python tools/refresh_schemas.py
Fetching openmhealth/schemas@main...
Diffing against omh_shim/schemas/...
  omh_heart-rate_2-0.json: unchanged
  omh_sleep-duration_2-0.json: CHANGED (3 lines)
    ...diff preview...
Update these files? [y/N]
```

## The 12 converters

Each converter is a pure function: one source-schema dict in, one OMH-schema dict out. Below, each is described with its source input shape, its target OMH schema, and the key mapping decisions. Implementation details (exact field paths, unit conversions) are left to the implementation plan — this spec documents the *what*, not the *how*.

### `ow_normalized` source

All six `ow_normalized` converters consume dicts shaped like OW's `TimeSeriesSample`, `ActivitySummary`, or `Workout` as defined in `the-momentum/open-wearables` under `backend/app/schemas/responses/activity/`. Callers are expected to pass the correct type for the requested `data_type` — the dispatch does not auto-detect.

1. **`heart_rate`** — input: a single `TimeSeriesSample` with `type="heart_rate"`, `value` (int bpm), `timestamp` (datetime), `zone_offset`. Output: `omh:heart-rate:2.0` with `body.heart_rate.value`, `body.effective_time_frame.date_time`, etc. Unit always `beats/min`.

2. **`heart_rate_variability`** — input: a single `TimeSeriesSample` with `type="heart_rate_variability"`, `value` (float ms), `timestamp`. Output: depends on whether OMH publishes an HRV schema (see **Implementation flag** below). If not, `ieee:heart-rate-variability:1.0` or an inline custom schema.

3. **`step_count`** — input: a single `TimeSeriesSample` with `type="steps"`, `value` (int), `timestamp`, **OR** an `ActivitySummary` dict with `steps`, `date`. Output: `omh:step-count:3.0`. The converter must handle both shapes (OW exposes steps both as timeseries and as daily rollups).

4. **`sleep_duration`** — input: an `ActivitySummary`-shaped dict carrying sleep fields, specifically `sleep_total_duration_minutes`, `sleep_time_in_bed_minutes`, `date`. Output: `omh:sleep-duration:2.0` with `body.sleep_duration.value` (in seconds), `body.effective_time_frame.time_interval`.

5. **`sleep_episode`** — input: a structured sleep event with `bedtime_start`, `bedtime_end`, and a `sleep_stages` array. Output: `omh:sleep-episode:1.1` with `body.sleep_episode.time_interval`, `body.sleep_episode.total_sleep_time`, and stage summaries. **This is the hardest converter** — it translates OW's per-minute stage arrays into OMH's stage-summary form.

6. **`physical_activity`** — input: an `ActivitySummary` dict with `steps`, `active_calories_kcal`, `distance_meters`, `active_minutes`, `date`. Output: `omh:physical-activity:2.0` with the corresponding body fields. The `source.device_model` from OW's `SourceMetadata` maps to `header.acquisition_provenance.source_name`.

### `oura_raw` source

All six `oura_raw` converters consume dicts shaped like an individual item in Oura's `/v2/usercollection/<endpoint>/data[i]` array. The converter expects one item, not the whole response envelope. Callers are expected to unwrap the envelope before calling `convert()`.

These converters port mapping logic from `dicristea/oura-clinical-workbench/data_syn`. Each source file includes a header comment crediting the upstream project.

7. **`heart_rate`** — input: an item from Oura's `/v2/usercollection/heartrate/data`, with `bpm` (int), `timestamp` (ISO string), `source` (string). Output: `omh:heart-rate:2.0`. 1:1 mapping, straightforward.

8. **`heart_rate_variability`** — input: an item from Oura's `/v2/usercollection/daily_readiness/data` (or similar), extracting the HRV field. Output: same target as `ow_normalized.heart_rate_variability`.

9. **`step_count`** — input: an item from Oura's `/v2/usercollection/daily_activity/data`, extracting the `steps` field. Output: `omh:step-count:3.0`. Note: this is a daily rollup, so the `effective_time_frame.time_interval` spans the day.

10. **`sleep_duration`** — input: an item from Oura's `/v2/usercollection/daily_sleep/data` with `contributors.total_sleep` or similar. Output: `omh:sleep-duration:2.0`. Uses `_sleep_interval()`-style logic from dicristea's code (parsing `bedtime_start`, `bedtime_end`, computing duration).

11. **`sleep_episode`** — input: an item from Oura's `/v2/usercollection/sleep/data` (a detailed sleep session). Output: `omh:sleep-episode:1.1`. Most complex of the Oura converters — handles the `sleep_phase_5_min` bitstring, latencies, and stage durations.

12. **`physical_activity`** — input: an item from Oura's `/v2/usercollection/daily_activity/data` with `active_calories`, `equivalent_walking_distance`, `low_activity_time`, `medium_activity_time`, `high_activity_time`. Output: `omh:physical-activity:2.0`.

### Implementation flag: heart-rate-variability schema

OMH's published schema catalog may not include a formal `heart-rate-variability` schema at v1.0. If it does not, the implementation plan must resolve this in one of three ways:

- **(a)** Use `ieee:heart-rate-variability:1.0` from the IEEE schemas that dicristea's code references
- **(b)** Define an inline custom schema inside `omh_shim/schemas/` marked as non-standard in its README
- **(c)** Drop `heart_rate_variability` from v0.1 scope and defer to v0.2 after researching the OMH ecosystem

The implementation plan should explicitly document the choice and reasoning.

## Testing strategy

### Unit tests

Each converter gets at least **3 fixture pairs** in `tests/fixtures/<source>/`:

- `<converter>_input_happy.json` — a realistic, fully-populated sample
- `<converter>_input_minimal.json` — only required fields present
- `<converter>_input_edge.json` — an edge case specific to the converter (missing optional fields, boundary values, unusual units)

Each paired with an expected output file:
- `<converter>_expected_happy.json`
- `<converter>_expected_minimal.json`
- `<converter>_expected_edge.json`

Test functions are parameterized over all fixtures for a given source:

```python
# tests/test_ow_normalized.py
import pytest
from pathlib import Path
from omh_shim import convert

@pytest.mark.parametrize("fixture", list(Path("tests/fixtures/ow_normalized").glob("*_input_*.json")))
def test_ow_normalized_conversion(fixture):
    input_data = json.loads(fixture.read_text())
    expected_path = fixture.with_name(fixture.name.replace("_input_", "_expected_"))
    expected = json.loads(expected_path.read_text())
    converter_name = fixture.stem.split("_input_")[0]
    result = convert(source="ow_normalized", data_type=converter_name, sample=input_data)
    assert result == expected
```

**12 converters × 3 fixture pairs = 36 core test cases.** Plus:

- `test_dispatch.py` — verifies registry is populated, `ConversionError` raised for unknown pairs
- `test_schema_loader.py` — verifies all 6 OMH schemas load without error
- `test_validate.py` — verifies valid outputs pass and invalid outputs raise `ValidationError`
- A handful of negative tests (malformed input, unit conversion edge cases) per converter

### Validation as a test crutch

Because `validate=True` is the default, **every successful unit test run is also implicitly validating that every converter output conforms to its target OMH schema.** The unit tests don't need to re-check this — if a converter produces invalid output, the conversion call raises `ValidationError` before the assertion runs, and the test fails with a clear message.

### CI

GitHub Actions workflow at `.github/workflows/test.yml`:

```yaml
name: test
on: [push, pull_request]
jobs:
  test:
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: pytest
```

## Distribution

### Production / CI install (git URL)

JHE's `Pipfile` pins to a tag or main commit:

```toml
[packages]
omh-shim = {git = "https://github.com/<org>/omh-shim.git", ref = "v0.1.0"}
```

### Local-dev install (editable local path)

For iterating on both repos simultaneously, developers override the Pipfile with a local `Pipfile.local` or environment variable pointing to a sibling checkout:

```toml
# Pipfile.local (gitignored)
[packages]
omh-shim = {path = "../omh-shim", editable = true}
```

The JHE repo's README documents this workflow in a new "Working on omh-shim locally" section.

### PyPI

Not in v0.1 scope. If and when the library has external adopters beyond JHE, publishing to PyPI becomes worthwhile. Until then, git URL install is sufficient.

## Licensing and attribution

### Library license

MIT. `LICENSE` file at the repo root is the standard MIT text. `pyproject.toml` declares `license = {text = "MIT"}`.

### Attribution for `oura_raw` source

Every converter file under `omh_shim/sources/oura_raw/` carries a header comment:

```python
"""Oura `/v2/usercollection/daily_sleep` → omh:sleep-duration:2.0 converter.

Ported with permission from dicristea/oura-clinical-workbench by <student name>,
part of JP Prosser's research group. See AUTHORS.md for full credit.

Original reference: https://github.com/dicristea/oura-clinical-workbench/blob/main/data_syn/scripts/oura_standard_converter.py
"""
```

`AUTHORS.md` at the repo root lists:

- JupyterHealth Exchange team (primary maintainer)
- The dicristea author(s) of the `data_syn` workbench (oura_raw converter logic reference)

`README.md` includes a "Credits" section calling out the upstream reference.

### Known documentation gap (follow-up action item)

The upstream repo `dicristea/oura-clinical-workbench` has no `LICENSE` file on GitHub as of 2026-04-09. The author has granted verbal permission for this port, but the permission is not currently documented in a form independent of private correspondence. **Follow-up action (not a blocker for v0.1 implementation):** ask the upstream author to add an MIT `LICENSE` file to their repo and reference it in our `AUTHORS.md`.

## v0.2 roadmap (informational, not part of v0.1 scope)

These are deferred to v0.2 and are listed so contributors know what's coming:

### Additional OMH data types (both sources)

- `calories_burned` → `omh:calories-burned:2.0`
- `body_temperature` → `omh:body-temperature:4.0`
- `oxygen_saturation` → `omh:oxygen-saturation:2.0`
- `respiratory_rate` → `omh:respiratory-rate:2.0`
- `blood_pressure` → `omh:blood-pressure:4.0` (probably only relevant for sources other than Oura)
- `workout` → `omh:physical-activity:2.0` (workout-specific mapping, distinct from daily summary)

### Additional sources

- `garmin_raw` — Garmin Health API response shapes
- `fitbit_raw` — Fitbit Web API response shapes
- `apple_health` — Apple HealthKit export XML → OMH
- `ow_raw` — if Open Wearables ever ships the raw-passthrough proposal from `docs/open-wearables-upstream-proposals.md`, add a thin adapter that wraps the `oura_raw` converters with OW-shape unwrapping

## Decision log

Decisions locked in during the 2026-04-09 brainstorm session with the spec owner. Alternatives considered and rejected are captured here so future reviewers understand the reasoning.

### D10. Library split and boundaries

**Decision:** `omh-shim` is an external pip-installable package. JHE consumes it via a thin internal adapter (`core/services/ow_ingest/omh_to_fhir.py`, specified separately) that wraps OMH output in a FHIR Observation dict and hands it to the existing `Observation.fhir_create()`. The existing `Observation.fhir_create()` is unchanged — its existing "plain OMH JSON attachment" branch (line 1264 in `core/models.py`) already handles what the new pipeline produces.

**Repo name:** `omh-shim`, rewriting the existing repo from scratch. Old commit history is archived (not force-pushed over).

**Distribution:** git URL in `Pipfile` for production/CI, editable local-path install supported via `Pipfile.local` override for local dev. No PyPI publish for v0.1.

**Public API:** `convert(source: str, data_type: str, sample: dict, *, validate: bool = True) -> dict`. Raises `ConversionError` for unknown dispatch keys or malformed inputs; raises `ValidationError` if output fails OMH schema validation (only when `validate=True`).

**Output validation:** on by default. The opt-out flag exists for hypothetical high-throughput callers but is not used by JHE.

**Schemas:** vendored into `omh_shim/schemas/` and loaded via `importlib.resources`. Refreshed manually from `openmhealth/schemas` when upstream publishes new versions.

**Rejected alternatives:**

- *Single JHE-internal module (no separate repo).* Rejected: the OW-to-OMH mapping is not JHE-specific — other Open mHealth consumers would benefit from a shared library. Burying it in JHE's repo prevents reuse.
- *Single pip package containing both the shim and FHIR wrapping.* Rejected: FHIR is a JHE-specific concern. Coupling it into the shim would pollute the shim's dependency surface with `fhir.resources`, `pyhumps`, etc., and would force any future non-FHIR consumer to inherit those deps.
- *Stock filesystem schema loading (JHE's current approach).* Rejected: breaks the "pip install and go" principle. Every consumer would have to ensure schema files live in a specific directory.

### D16. License model for dicristea-derived code

**Decision:** The author of `dicristea/oura-clinical-workbench` has granted permission to port the `data_syn` converter logic into `omh-shim` with attribution. Attribution is implemented as source-file header comments, an `AUTHORS.md` file, and a README credit.

**Known documentation gap (follow-up, not blocking):** the upstream repo has no `LICENSE` file on GitHub. Ask the upstream author to add MIT.

**Rejected alternatives:**

- *Vendor the code verbatim without porting.* Rejected: the upstream code is a CLI workbench with filesystem I/O and config-file dispatch, incompatible with `omh-shim`'s pure-function contract.
- *Block v0.1 on upstream adding a LICENSE file.* Rejected: verbal permission is sufficient to proceed; the license file is a nice-to-have for long-term clarity but not a legal blocker given the grant.
- *Ship v0.1 without any Oura-raw support and defer to v0.2.* Rejected: losing the multi-source story at launch weakens the library's framing and means the architecture is unexercised in v0.1.

### Scope decision. v0.1 = 12 converters

**Decision:** v0.1 ships all 12 converters — 6 OMH target data types (`heart_rate`, `heart_rate_variability`, `step_count`, `sleep_duration`, `sleep_episode`, `physical_activity`) × 2 sources (`ow_normalized`, `oura_raw`).

**Rejected alternatives:**

- *v0.1 = 6 converters (one source only).* Rejected: the dispatch layer is over-engineered for a single source, and the multi-source architecture doesn't get exercised until v0.2. Launch story is weaker.
- *v0.1 = 3 converters × 2 sources = 6 total.* Rejected: thinner feature set, and the JHE polling MVP it feeds into would have noticeable gaps (no HRV, no sleep episode). The extra work for full 6-data-type coverage pays off in downstream completeness.

**Trade-off acknowledged:** Option X is the largest v0.1 scope available. The `sleep_episode` converter in particular is a known complexity hotspot. Implementation plan should schedule `sleep_episode` toward the end of the task list so more-tractable converters build momentum and test infrastructure first.

### D17. Converter input granularity

**Decision:** API signature is `convert(source, data_type, sample) -> dict` where `data_type` names the **OMH target schema**, not the source endpoint. When a source item (e.g. Oura `daily_activity`) produces multiple OMH records, the caller calls `convert()` multiple times with the same source item and different `data_type` values.

**Rejected alternatives:**

- *`convert() -> list[dict]`.* Rejected: awkward ergonomics for the trivial 1:1 case (most converters return single-element lists).
- *Add a third `target` parameter distinct from `data_type`.* Rejected: blows up the dispatch matrix, adds caller-side complexity, and conflates two ideas (source endpoint vs OMH target).

**Flag for implementation:** converters must document their expected input shape in a module-level docstring so callers know whether to pass a `TimeSeriesSample`, an `ActivitySummary`, a Workout, an Oura `daily_activity` item, etc. The library does not auto-detect input shape.

### Other locked-in decisions (not numbered because they were straightforward)

- **Python version support:** 3.11+. Matches JHE's current runtime and allows modern type syntax.
- **Type hints:** used throughout, no `mypy --strict` gate for v0.1 (added in v0.2 if it pays off).
- **Versioning scheme:** semver. v0.1.0 first, minor bumps for new converters, major bump reserved for any breaking change to the public `convert()` signature.
- **Linter / formatter:** `ruff` for both. `ruff format` on commit, `ruff check` in CI.
- **JSON schema library:** `jsonschema` (the canonical Python implementation). No custom validation.
- **Dependencies:** `jsonschema` is the only runtime dependency. Dev deps: `pytest`, `pytest-cov`, `ruff`.

## Open questions for the implementation plan

The following items were deliberately left for the writing-plans phase because they are resolvable in that phase without blocking this spec. Listing them here so they don't get lost:

1. **Exact OMH schema filenames.** The `openmhealth/schemas` repo uses hyphen-separated names like `heart-rate-2.0.json` in some places and `omh_heart-rate_2-0.json` in others. The implementation plan must pick one naming convention and apply it consistently in `omh_shim/schemas/`.

2. **HRV target schema.** Per the "Implementation flag" note above, the v0.2 converter for `heart_rate_variability` needs a concrete target schema decision (OMH standard, IEEE, or inline custom).

3. **Exact source payload samples for fixtures.** The implementation plan will need real sample payloads from OW's read API and from Oura's v2 API to build test fixtures against. These can be captured from the existing JHE dev environment (which already has OW running) and from the Oura sandbox.

4. **`sleep_phase_5_min` bitstring parsing.** Oura's sleep endpoint encodes per-minute sleep stages as a character bitstring. The implementation plan for the `oura_raw.sleep_episode` converter must include the decoding logic — likely a direct port from dicristea's `record_builder.py`.

5. **Old `omh_shim` repo archival.** Decide whether to force-push-overwrite the existing `omh_shim` repo, or create a new repo and archive the old one. The choice affects git history but not functionality. Recommended: archive old, create new, because it preserves the PoC history for reference.
