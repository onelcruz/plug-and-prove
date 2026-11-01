"""Deterministic probe inputs for the conformance harness (research.md R3).

The harness runs each adapter on probe streams in addition to the real stream so
checks 5-7 have evidence even when no target is in view. Nothing here is random
(constitution Principle V).
"""

from __future__ import annotations

import math

from src.config.models import ScenarioConfig, SensorConfig
from src.simulator.detections import RawDetection, expected_ticks
from src.simulator.geo import offset_to_latlon


def sensor_position(sensor: SensorConfig, scenario: ScenarioConfig) -> tuple[float, float]:
    """Sensor lat/lon: configured position, else the defended-area center."""
    lat = sensor.lat if sensor.lat is not None else scenario.defended_area.center_lat
    lon = sensor.lon if sensor.lon is not None else scenario.defended_area.center_lon
    return lat, lon


def probe_position(sensor: SensorConfig, scenario: ScenarioConfig) -> tuple[float, float, float]:
    """Fixed probe target: due east of the sensor by ``range_m / 2``, mid-band altitude.

    Inside check 3's coverage circle and check 2's altitude bounds by construction.
    """
    base_lat, base_lon = sensor_position(sensor, scenario)
    lat, lon = offset_to_latlon(base_lat, base_lon, sensor.range_m / 2.0, 0.0)
    return lat, lon, (scenario.min_alt_m + scenario.max_alt_m) / 2.0


def withheld_tick_indices(sensor: SensorConfig, scenario: ScenarioConfig) -> frozenset[int]:
    """Indices of the contiguous run of ticks the gap probe withholds.

    The run spans more than ``heartbeat_timeout_s``, starts at ``n // 3``, and is
    clamped so at least one tick is supplied before and after it. A schedule too
    short for that yields an empty set.
    """
    n_ticks = len(expected_ticks(sensor.update_rate_hz, scenario.duration_s))
    run_length = math.ceil(2.0 * sensor.heartbeat_timeout_s * sensor.update_rate_hz)
    start = n_ticks // 3
    start = max(start, 1)
    run_length = min(run_length, n_ticks - 1 - start)
    if run_length <= 0:
        return frozenset()
    return frozenset(range(start, start + run_length))


def build_probe_stream(
    sensor: SensorConfig,
    scenario: ScenarioConfig,
    withheld: frozenset[int] = frozenset(),
) -> list[RawDetection]:
    """One ``RawDetection`` per scheduled tick at the probe position, minus ``withheld`` ticks."""
    lat, lon, alt_m = probe_position(sensor, scenario)
    return [
        RawDetection(
            sensor_id=sensor.sensor_id,
            t_s=t_s,
            lat=lat,
            lon=lon,
            alt_m=alt_m,
            accuracy_m=sensor.accuracy_m,
        )
        for i, t_s in enumerate(expected_ticks(sensor.update_rate_hz, scenario.duration_s))
        if i not in withheld
    ]
