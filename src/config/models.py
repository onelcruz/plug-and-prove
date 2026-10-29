"""Pydantic models for scenario and sensor configuration (architecture.md §2).

- The scenario simulator issue (#5) extends ``ScenarioConfig`` with
  ``duration_s`` and ``drones``/``birds``/``clutter`` target definitions, and
  adds optional ``lat``/``lon`` placement to ``SensorConfig`` (defaults to the
  defended area's center when omitted, so existing sensor YAML files remain
  valid unchanged).
- The sensor adapter contract issue (#6) and conformance harness issue (#7)
  will likely extend ``SensorConfig`` further with fields such as
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


class DroneTarget(BaseModel):
    """A simulated drone that approaches the defended area in a straight line.

    It starts ``start_range_m`` from the area's center, at compass bearing
    ``start_bearing_deg``, and flies a straight line through the center and
    out the opposite side at constant ``speed_mps`` and ``altitude_m``.
    """

    target_id: str
    start_bearing_deg: float = Field(..., ge=0.0, lt=360.0)
    start_range_m: PositiveFloat
    speed_mps: PositiveFloat
    altitude_m: PositiveFloat


class BirdTarget(BaseModel):
    """A simulated bird: a slower, erratic random walk near the area.

    Distinct from a drone's straight-line approach so a later classifier has
    a measurable statistical difference (heading changes, speed, altitude).
    """

    target_id: str
    start_lat: float = Field(..., ge=-90, le=90)
    start_lon: float = Field(..., ge=-180, le=180)
    speed_mps: PositiveFloat
    altitude_m: PositiveFloat
    heading_change_period_s: PositiveFloat = 3.0


class ClutterConfig(BaseModel):
    """Random, short-lived, stationary clutter blips within the area.

    Each blip appears at a random time and location, persists for
    ``dwell_s`` with zero velocity, then disappears -- distinct from both
    drones (fast, linear) and birds (slower, but still moving).
    """

    count: int = Field(..., ge=0)
    altitude_m: PositiveFloat = 50.0
    dwell_s: PositiveFloat = 1.0


class ScenarioConfig(BaseModel):
    """Top-level scenario definition: name, seed, duration, and targets."""

    name: str
    seed: int
    duration_s: PositiveFloat
    defended_area: DefendedArea
    drones: list[DroneTarget] = Field(default_factory=list)
    birds: list[BirdTarget] = Field(default_factory=list)
    clutter: ClutterConfig | None = None


class SensorConfig(BaseModel):
    """Per-sensor configuration: accuracy, range, update rate, dropout.

    ``lat``/``lon`` place the sensor; if omitted, the simulator uses the
    scenario's defended-area center as the sensor's position.
    """

    sensor_id: str
    accuracy_m: PositiveFloat
    range_m: PositiveFloat
    update_rate_hz: PositiveFloat
    dropout_probability: float = Field(..., ge=0.0, le=1.0)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
