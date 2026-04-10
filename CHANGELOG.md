# Changelog

All notable changes to omh-shim are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed — BREAKING

- `convert()` now takes a keyword-only ``tz`` parameter. Daily data types
  (`step_count`, `physical_activity`, `sleep_duration`) REQUIRE an explicit
  timezone so day boundaries reflect the user's local calendar day rather
  than silently assuming UTC. A Tokyo user's "April 9" is not UTC "April 9"
  — the previous behavior misaligned daily summaries by up to 24 hours for
  any non-UTC user.
- Naive (timezone-less) datetimes are now rejected with `ConversionError`
  at parse time. Silent coercion to UTC previously misrecorded a Tokyo
  user's "22:30" local time as "22:30 UTC".
- `heart_rate_variability` schema id renamed from
  `omh:heart-rate-variability:1.0` to `local:heart-rate-variability:1.0`.
  Open mHealth has not published a canonical HRV schema; the `local:`
  namespace prevents downstream consumers from assuming OMH-standard
  interoperability. Callers pinning the old id must update.
- `convert()` now wraps any `KeyError`/`ValueError`/`TypeError` from
  converters as `ConversionError` so the public contract ("invalid sample
  shape raises ConversionError") actually holds. Previously converters
  leaked raw `KeyError` in several paths.

### Added

- Positive and negative regression tests for all timezone behavior,
  parametrized across every (source, data_type) pair that parses datetimes
  or aggregates days.
- Import-time invariant check: `REGISTRY` and `_SCHEMA_ID` must stay in
  sync, so adding a converter without its schema id fails fast at import.

### Fixed

- `_validate.Draft7Validator` is now cached per schema id via `lru_cache`
  instead of rebuilt on every `convert()` call — real speedup for bulk
  ingest workloads.

### Refactored (non-behavioral)

- Converters raise `ConversionError` directly rather than relying on the
  `convert()` wrapper to translate raw `KeyError`. The exception type is
  part of the contract, not an implementation detail of the wrapper.

## [0.1.0] — 2026-04-09

### Added

- Initial release of `omh-shim`.
- Public API: `convert(source, data_type, sample, *, validate=True) -> dict`,
  `ConversionError`, `ValidationError`.
- Sources: `ow_normalized` (Open Wearables read-API response shapes) and
  `oura_raw` (Oura v2 API response items).
- Data types: `heart_rate`, `heart_rate_variability`, `step_count`,
  `sleep_duration`, `sleep_episode`, `physical_activity` — 12 converters total.
- Vendored OMH JSON schemas (5 standard + 1 local HRV placeholder + 13
  transitive `$ref` dependencies) loaded via `importlib.resources`.
- `referencing.Registry`-based ref resolution so `Draft7Validator` resolves
  cross-schema `$ref` strings to local files without network access.
- Output validation by default with `validate=False` opt-out.
- 26 unit tests covering all 12 converters plus edge cases.

### Attribution

- `omh_shim/sources/oura_raw/` ports converter mapping logic from
  [dicristea/oura-clinical-workbench/data_syn](https://github.com/dicristea/oura-clinical-workbench/tree/main/data_syn)
  with permission. Each `oura_raw` source file carries an attribution header.

### Known limitations

- No real-data fixtures yet; the test fixtures are hand-written from OW's
  pydantic response schemas and Oura v2 API docs. Real-data validation will
  happen when JupyterHealth Exchange's polling pipeline starts consuming
  this library against live OW and Oura sandbox endpoints.
- The `oura_raw.heart_rate_variability` converter requires an explicit
  millisecond value (`rmssd` or `contributors.hrv_balance_ms`); it refuses
  to convert Oura's normalized 0–100 `hrv_balance` score because that score
  is not a valid HRV measurement in milliseconds.
- `omh:physical-activity:1.2` is the latest version available upstream. The
  spec mentioned 2.0; that version does not exist in `openmhealth/schemas`.
