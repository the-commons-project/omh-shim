# omh-shim

Convert wearable health data from vendor schemas to [Open mHealth](https://www.openmhealth.org/) schemas.

## Status

v0.1 under active development. Public API is stable; converter coverage is expanding.

## Install

```bash
pip install git+https://github.com/surfdoc/omh-shim.git@v0.1.0
```

## Usage

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

`convert` raises `ConversionError` for unknown `(source, data_type)` pairs and `ValidationError` if the converter output fails OMH schema validation.

## Supported sources and data types (v0.1)

| `source` | `data_type` values |
|---|---|
| `ow_normalized` | `heart_rate`, `heart_rate_variability`, `step_count`, `sleep_duration`, `sleep_episode`, `physical_activity` |
| `oura_raw` | `heart_rate`, `heart_rate_variability`, `step_count`, `sleep_duration`, `sleep_episode`, `physical_activity` |

## Design and decisions

- Spec: [`docs/specs/2026-04-09-omh-shim-design.md`](docs/specs/2026-04-09-omh-shim-design.md)
- Plan: [`docs/plans/2026-04-09-omh-shim-v0.1.md`](docs/plans/2026-04-09-omh-shim-v0.1.md)

## Credits

`omh_shim/sources/oura_raw/` ports converter mapping logic with permission from [dicristea/oura-clinical-workbench](https://github.com/dicristea/oura-clinical-workbench/tree/main/data_syn). See [AUTHORS.md](AUTHORS.md).

## License

MIT. See [LICENSE](LICENSE).
