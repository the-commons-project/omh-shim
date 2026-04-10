# omh-shim

Convert wearable health data from vendor schemas to [Open mHealth](https://www.openmhealth.org/) schemas.

## Status

v0.1 under active development. Public API is stable; converter coverage is expanding.

## Install

```bash
pip install git+https://github.com/surfdoc/omh-shim.git@v0.1.0
```

## Usage

Timestamp-based data types (one reading at a known instant):

```python
from omh_shim import convert

omh_record = convert(
    source="ow_normalized",
    data_type="heart_rate",
    sample={
        "timestamp": "2026-04-09T08:30:00+00:00",
        "type": "heart_rate",
        "value": 72,
        "unit": "bpm",
        "source": {"source_name": "Oura Ring", "device_model": "Oura Gen 3"},
    },
)
```

Daily data types (``step_count``, ``physical_activity``, ``sleep_duration``)
aggregate over a calendar day, so they REQUIRE an explicit timezone so the day
boundaries reflect the user's local day rather than silently assuming UTC:

```python
from datetime import UTC
from zoneinfo import ZoneInfo

# UTC-anchored upstream data
convert(
    source="oura_raw",
    data_type="step_count",
    sample={"day": "2026-04-09", "steps": 8432},
    tz=UTC,
)

# User's local timezone
convert(
    source="oura_raw",
    data_type="step_count",
    sample={"day": "2026-04-09", "steps": 8432},
    tz=ZoneInfo("America/Los_Angeles"),
)
```

`convert` raises `ConversionError` for unknown `(source, data_type)` pairs,
invalid sample shapes, naive (timezone-less) datetimes, or a missing ``tz``
for daily data types. It raises `ValidationError` if the converter output
fails schema validation.

## Supported sources and data types (v0.1)

| `source` | `data_type` values |
|---|---|
| `ow_normalized` | `heart_rate`, `heart_rate_variability`, `step_count`, `sleep_duration`, `sleep_episode`, `physical_activity` |
| `oura_raw` | `heart_rate`, `heart_rate_variability`, `step_count`, `sleep_duration`, `sleep_episode`, `physical_activity` |

Note: `heart_rate_variability` targets the local placeholder schema
`local:heart-rate-variability:1.0` (Open mHealth has not published a canonical
HRV schema as of 2026-04). The `local:` namespace is deliberate — downstream
consumers should not assume OMH-standard interoperability for HRV records.

## Mapping references

Field-by-field documentation of what each converter maps, what it skips, and why:

- [`docs/mappings/oura_raw.md`](docs/mappings/oura_raw.md) — Oura Ring v2 API → OMH
- [`docs/mappings/ow_normalized.md`](docs/mappings/ow_normalized.md) — Open Wearables normalized API → OMH

## Credits

`omh_shim/sources/oura_raw.py` ports converter mapping logic with permission
from [dicristea/oura-clinical-workbench](https://github.com/dicristea/oura-clinical-workbench/tree/main/data_syn).
See [AUTHORS.md](AUTHORS.md).

## License

MIT. See [LICENSE](LICENSE).
