# omh-shim

Convert wearable health data from vendor schemas to [Open mHealth](https://www.openmhealth.org/) schemas.

Single-file, zero-dependency Python library. Converts Oura Ring v2 and Open
Wearables normalized samples to IEEE 1752.1 data-point envelopes.

## Status

v0.2 under active development. Public API is stable; converter coverage is expanding.

## Install

```bash
pip install git+https://github.com/surfdoc/omh-shim.git@v0.2.0
```

No runtime dependencies. Pure Python 3.11+.

## Usage

Timestamp-based data types (one reading at a known instant):

```python
from omh_shim import to_omh

record = to_omh(
    "ow_normalized", "heart_rate",
    {
        "timestamp": "2026-04-09T08:30:00+00:00",
        "type": "heart_rate",
        "value": 72,
        "unit": "bpm",
        "source": {"source_name": "Oura Ring", "device_model": "Oura Gen 3"},
    },
)
```

Daily data types (`step_count`, `physical_activity`, `sleep_duration`) aggregate
over a calendar day and REQUIRE an explicit timezone — day boundaries depend on
the user's local day, not UTC:

```python
from datetime import UTC
from zoneinfo import ZoneInfo

# UTC-anchored upstream data
to_omh("oura_raw", "step_count", {"day": "2026-04-09", "steps": 8432}, tz=UTC)

# User's local timezone
to_omh(
    "oura_raw", "step_count",
    {"day": "2026-04-09", "steps": 8432},
    tz=ZoneInfo("America/Los_Angeles"),
)
```

Every call returns the full IEEE 1752.1 data-point envelope:

```python
{
    "header": {
        "uuid": "...",
        "schema_id": {"namespace": "omh", "name": "heart-rate", "version": "2.0"},
        "source_creation_date_time": "...",
        "modality": "sensed",
        "external_datasheets": [...],  # auto-populated from sample["source"] if present
    },
    "body": {
        "heart_rate": {"value": 72.0, "unit": "beats/min"},
        "effective_time_frame": {"date_time": "2026-04-09T08:30:00Z"},
    },
}
```

`to_omh` raises `ConvertError` for unknown `(source, data_type)` pairs, invalid
sample shapes, naive (timezone-less) datetimes, or a missing `tz` for daily
data types.

## Supported sources and data types

| `source` | `data_type` values |
|---|---|
| `ow_normalized` | `heart_rate`, `heart_rate_variability`, `step_count`, `sleep_duration`, `sleep_episode`, `physical_activity`, `oxygen_saturation` |
| `oura_raw` | `heart_rate`, `heart_rate_variability`, `step_count`, `sleep_duration`, `sleep_episode`, `physical_activity` |

Note: `heart_rate_variability` targets the local placeholder schema
`local:heart-rate-variability:1.0` (Open mHealth has not published a canonical
HRV schema as of 2026-04). The `local:` namespace is deliberate — downstream
consumers should not assume OMH-standard interoperability for HRV records.

## Schema validation

The library does not validate its output against JSON schemas at runtime —
correctness is enforced by the test suite, which validates every converter
output against the vendored OMH schemas using `jsonschema`. If your application
needs runtime validation, install `jsonschema` and validate on your side.

The vendored schemas ship with the package under `omh_shim.schemas` for
reference and for downstream runtime validation if you need it.

## Mapping references

- [`docs/mappings/oura_raw.md`](docs/mappings/oura_raw.md) — Oura Ring v2 API → OMH (body fields)
- [`docs/mappings/ow_normalized.md`](docs/mappings/ow_normalized.md) — Open Wearables normalized API → OMH (body fields)
- [`docs/mappings/ieee-1752-header.md`](docs/mappings/ieee-1752-header.md) — IEEE 1752.1 data-point header envelope

## Credits

Oura converter mapping logic ported with permission from
[dicristea/oura-clinical-workbench](https://github.com/dicristea/oura-clinical-workbench/tree/main/data_syn).
See [AUTHORS.md](AUTHORS.md).

## License

MIT. See [LICENSE](LICENSE).
