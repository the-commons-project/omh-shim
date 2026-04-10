# IEEE 1752.1 Data-Point Header

When `convert(..., header=True)` is called, the output is wrapped in the standard IEEE 1752.1 data-point envelope. This page documents the header structure. The body content is documented per-source in [oura_raw.md](oura_raw.md) and [ow_normalized.md](ow_normalized.md).

## Envelope structure

```json
{
  "header": { ... },
  "body": { ... }
}
```

The header conforms to the IEEE 1752.1 `header-1.0.json` schema.

## Header fields

| Field | Required | Value | Notes |
|---|---|---|---|
| `uuid` | yes | RFC 4122 UUID4 | Generated fresh per `convert()` call |
| `schema_id.namespace` | yes | `"omh"` or `"local"` | Parsed from the schema id (e.g. `omh:heart-rate:2.0`) |
| `schema_id.name` | yes | e.g. `"heart-rate"` | |
| `schema_id.version` | yes | e.g. `"2.0"` | |
| `source_creation_date_time` | yes | ISO-8601 UTC | Timestamp at conversion time, not the measurement time |
| `modality` | no | `"sensed"` | Always sensed — wearable device data |
| `external_datasheets` | no | array of `{datasheet_type, datasheet_reference}` | Caller-provided; see below |

## external_datasheets

Optional metadata about the data source. Pass via `convert(..., external_datasheets=[...])`.

The JHE data-point examples use this to identify the device manufacturer:

```python
convert(
    ...,
    header=True,
    external_datasheets=[
        {"datasheet_type": "manufacturer", "datasheet_reference": "Oura"},
    ],
)
```

Per the IEEE schema, `datasheet_reference` is formally an IRI but in practice is used as a free-text identifier (as in the JHE examples).

## Fields NOT included

| Field | Reason |
|---|---|
| `acquisition_provenance` | Belongs to the older OMH data-point schema, not IEEE 1752.1. The IEEE `header-1.0.json` schema does not define it. |
| `acquisition_rate` | Not applicable — omh-shim converts individual samples, not continuous streams with a fixed sampling rate. |

## Schema reference

The authoritative schema is `header-1.0.json` from the IEEE 1752.1 working group, vendored in JHE at `data/omh/json-schemas/metadata/header-1.0.json`. The `$id` is `https://w3id.org/ieee/ieee-1752-schema/header.json`.
