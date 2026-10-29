"""Pydantic models for scenario and sensor configuration (architecture.md §2).

These schemas are intentionally minimal for the scaffolding issue (#4):

- The scenario simulator issue (#5) is expected to extend ``ScenarioConfig``
  with full target-path, bird, and clutter generation parameters.
- The sensor adapter contract issue (#6) and conformance harness issue (#7)
  will likely extend ``SensorConfig`` with fields such as
  ``max_clock_offset_s`` and ``heartbeat_timeout_s`` as they're implemented.

Extend these models in those issues rather than redefining them elsewhere.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, PositiveFloat


class DefendedArea(BaseModel):
    """A circular defended area used to bound the demo scenario."""

    center_lat: float = Field(..., ge=-90, le=90)
    center_lon: float = Field(..., ge=-180, le=180)
    radius_m: PositiveFloat


class ScenarioConfig(BaseModel):
    """Top-level scenario definition: name, seed, and defended area."""

    name: str
    seed: int
    defended_area: DefendedArea


class SensorConfig(BaseModel):
    """Per-sensor configuration: accuracy, range, update rate, dropout."""

    sensor_id: str
    accuracy_m: PositiveFloat
    range_m: PositiveFloat
    update_rate_hz: PositiveFloat
    dropout_probability: float = Field(..., ge=0.0, le=1.0)
