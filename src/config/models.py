"""Pydantic models for scenario and sensor configuration (architecture.md §2).

- The scenario simulator issue (#5) extends ``ScenarioConfig`` with
  ``duration_s`` and ``drones``/``birds``/``clutter`` target definitions, and
  adds optional ``lat``/``lon`` placement to ``SensorConfig`` (defaults to the
  defended area's center when omitted, so existing sensor YAML files remain
  valid unchanged).
- The sensor adapter contract issue (#6) extends ``ScenarioConfig`` with
  ``start_utc`` (a configured, deterministic Unix epoch reference required for
  reproducible ``timestamp_utc`` conversion -- see constitution Principle V)
  and ``SensorConfig`` with ``heartbeat_timeout_s``. The conformance harness
  issue (#7) will likely extend ``SensorConfig`` further with fields such as
  ``max_clock_offset_s`` as it's implemented.

Extend these models in those issues rather than redefining them elsewhere.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, NonNegativeFloat, PositiveFloat, model_validator


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
    start_utc: NonNegativeFloat
    defended_area: DefendedArea
    drones: list[DroneTarget] = Field(default_factory=list)
    birds: list[BirdTarget] = Field(default_factory=list)
    clutter: ClutterConfig | None = None


class SensorConfig(BaseModel):
    """Per-sensor configuration: accuracy, range, update rate, dropout.

    ``lat``/``lon`` place the sensor; if omitted, the simulator uses the
    scenario's defended-area center as the sensor's position.

    ``heartbeat_timeout_s`` must exceed one scheduled tick interval
    (``1 / update_rate_hz``) -- otherwise no config could ever satisfy
    architecture.md §3.4's "emit... within heartbeat_timeout_s" requirement.
    The validator uses a strict ``>``, not ``>=``, to avoid a boundary-
    equality case that float64 rounding could make fail downstream.
    """

    sensor_id: str
    accuracy_m: PositiveFloat
    range_m: PositiveFloat
    update_rate_hz: PositiveFloat
    dropout_probability: float = Field(..., ge=0.0, le=1.0)
    heartbeat_timeout_s: PositiveFloat
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def _validate_heartbeat_timeout(self) -> "SensorConfig":
        min_interval_s = 1.0 / self.update_rate_hz
        if self.heartbeat_timeout_s <= min_interval_s:
            raise ValueError(
                f"heartbeat_timeout_s ({self.heartbeat_timeout_s}) must be greater than "
                f"1 / update_rate_hz ({min_interval_s}); otherwise no scheduled tick could "
                "ever satisfy it."
            )
        return self
