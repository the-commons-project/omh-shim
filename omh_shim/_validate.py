"""Validate converter outputs against vendored OMH schemas."""

from jsonschema import Draft7Validator

from omh_shim._schema_loader import load as load_schema
from omh_shim.errors import ValidationError


def validate_output(output: dict, schema_id: str) -> None:
    """Validate ``output`` against the OMH schema identified by ``schema_id``.

    Raises ``ValidationError`` with a human-readable message listing all
    schema violations. Returns ``None`` on success.
    """
    schema = load_schema(schema_id)
    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(output), key=lambda e: list(e.absolute_path))
    if not errors:
        return
    pieces = []
    for e in errors:
        path = "/".join(str(p) for p in e.absolute_path) or "<root>"
        pieces.append(f"{path}: {e.message}")
    raise ValidationError(
        f"Output does not conform to {schema_id}: " + "; ".join(pieces)
    )
