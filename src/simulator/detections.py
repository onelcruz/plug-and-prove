"""Per-sensor raw, noisy, rate-limited detection generation.

Produces the "pre-adapter" ``RawDetection`` stream each simulated sensor
would emit -- the shape the sensor adapter contract (issue #6) will
translate into the canonical ``Detection`` message (architecture.md §3.1).

Deliberately *not* the canonical schema: timestamps are seconds since
scenario start (``t_s``), not a UTC epoch float. Converting sim-clock time
to ``timestamp_utc`` -- and potentially introducing a clock-offset bug --
is an adapter-layer concern (architecture.md §3.4, and the deliberately
buggy third adapter in issue #8), not the simulator's.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, NonNegativeFloat, PositiveFloat

from src.config.models import ScenarioConfig, SensorConfig
from src.simulator.geo import distance_m, latlon_to_offset, offset_to_latlon
from src.simulator.trajectories import TruthObject


class RawDetection(BaseModel):
    """A single raw, noisy detection as a simulated sensor would report it."""

    sensor_id: str
    t_s: NonNegativeFloat
    lat: float
    lon: float
    alt_m: float
    accuracy_m: PositiveFloat


def _sensor_position(sensor: SensorConfig, scenario: ScenarioConfig) -> tuple[float, float]:
    lat = sensor.lat if sensor.lat is not None else scenario.defended_area.center_lat
    lon = sensor.lon if sensor.lon is not None else scenario.defended_area.center_lon
    return lat, lon


def expected_ticks(update_rate_hz: float, duration_s: float) -> list[float]:
    """Return the full scheduled tick schedule for a given rate/duration.

    Shared between ``generate_sensor_detections`` (which samples truth objects
    at each tick) and the sensor adapter contract (issue #6), which must
    recompute the identical schedule to know which ticks were "accounted for"
    by a ``Detection`` vs. requiring a ``Heartbeat``.

    Note: this can omit a final partial tick -- e.g. ``duration_s=0.3`` at
    10 Hz yields ``[0.0, 0.1, 0.2]``, not ``[0.0, 0.1, 0.2, 0.3]`` -- this is
    existing, unchanged behavior, not a bug to fix here.
    """
    dt_s = 1.0 / update_rate_hz
    n_ticks = math.floor(duration_s / dt_s) + 1
    return [min(i * dt_s, duration_s) for i in range(n_ticks)]


def generate_sensor_detections(
    sensor: SensorConfig,
    scenario: ScenarioConfig,
    truth_objects: list[TruthObject],
    rng,
) -> list[RawDetection]:
    """Sample each truth object at the sensor's update rate, applying its noise model.

    At each tick, a truth object is reported only if it exists at that time
    (see ``TruthObject.position_at``) and is within ``sensor.range_m``, and
    is not independently dropped per ``sensor.dropout_probability``. Reported
    positions are perturbed by Gaussian noise with standard deviation
    ``sensor.accuracy_m`` meters, applied in local East/North meters and
    converted back to lat/lon.
    """
    sensor_lat, sensor_lon = _sensor_position(sensor, scenario)

    detections: list[RawDetection] = []
    for t_s in expected_ticks(sensor.update_rate_hz, scenario.duration_s):
        for obj in truth_objects:
            sample = obj.position_at(t_s)
            if sample is None:
                continue

            if distance_m(sensor_lat, sensor_lon, sample.lat, sample.lon) > sensor.range_m:
                continue  # out of range

            if rng.random() < sensor.dropout_probability:
                continue  # dropped

            east_m, north_m = latlon_to_offset(sensor_lat, sensor_lon, sample.lat, sample.lon)
            noisy_east_m = east_m + rng.normal(0.0, sensor.accuracy_m)
            noisy_north_m = north_m + rng.normal(0.0, sensor.accuracy_m)
            noisy_lat, noisy_lon = offset_to_latlon(
                sensor_lat, sensor_lon, noisy_east_m, noisy_north_m
            )

            detections.append(
                RawDetection(
                    sensor_id=sensor.sensor_id,
                    t_s=t_s,
                    lat=noisy_lat,
                    lon=noisy_lon,
                    alt_m=sample.alt_m,
                    accuracy_m=sensor.accuracy_m,
                )
            )

    return detections
