"""Exception types raised by omh-shim."""


class ConversionError(Exception):
    """Raised when a sample cannot be converted.

    Causes include: no converter registered for the given (source, data_type)
    pair; source sample is missing required fields; source sample shape does
    not match what the converter expects.
    """


class ValidationError(Exception):
    """Raised when converter output does not conform to its target OMH schema.

    Only raised when ``convert(..., validate=True)`` (the default).
    """
