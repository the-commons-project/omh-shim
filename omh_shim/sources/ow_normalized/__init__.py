"""Converters for Open Wearables normalized read-API response shapes.

Each converter module is imported here to register itself in the dispatch.
"""

from omh_shim.sources.ow_normalized import (  # noqa: F401
    heart_rate,
    heart_rate_variability,
    physical_activity,
    sleep_duration,
    sleep_episode,
    step_count,
)
