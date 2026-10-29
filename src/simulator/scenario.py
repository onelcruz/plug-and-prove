"""Top-level scenario simulation: ground truth + per-sensor raw detections.

This is the single entry point the orchestrator (src/orchestrator.py, #13)
and conformance/fusion work (#6+) will call: given a scenario config and a
list of sensor configs, produce reproducible ground truth and per-sensor
raw detection streams.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.config.models import ScenarioConfig, SensorConfig
from src.simulator.detections import RawDetection, generate_sensor_detections
from src.simulator.rng import spawn_rngs
from src.simulator.trajectories import (
    TruthObject,
    generate_bird_trajectory,
    generate_clutter_trajectories,
    generate_drone_trajectory,
)


@dataclass(frozen=True)
class SimulationResult:
    """Ground truth and per-sensor raw detections for one simulation run."""

    truth_objects: list[TruthObject]
    detections_by_sensor: dict[str, list[RawDetection]]


def build_truth_objects(scenario: ScenarioConfig, rng) -> list[TruthObject]:
    """Generate ground-truth trajectories for every configured drone, bird, and clutter blip.

    Generation order is deterministic (drones, then birds, then clutter, in
    each list's config order), so a fixed seed always produces the same
    sequence of random draws and therefore identical trajectories.
    """
    objects: list[TruthObject] = []
    for drone in scenario.drones:
        objects.append(generate_drone_trajectory(rng, scenario.defended_area, drone))
    for bird in scenario.birds:
        objects.append(
            generate_bird_trajectory(rng, scenario.defended_area, bird, scenario.duration_s)
        )
    if scenario.clutter is not None:
        objects.extend(
            generate_clutter_trajectories(
                rng, scenario.defended_area, scenario.clutter, scenario.duration_s
            )
        )
    return objects


def run_simulation(scenario: ScenarioConfig, sensors: list[SensorConfig]) -> SimulationResult:
    """Run the full scenario: generate ground truth, then each sensor's raw detections.

    Uses one independent, reproducible RNG stream per concern (ground truth,
    then one per sensor) via ``spawn_rngs``, so sensors' noise never
    correlates with ground truth or with each other, while the whole run
    remains fully determined by ``scenario.seed``.
    """
    rngs = spawn_rngs(scenario.seed, 1 + len(sensors))
    truth_rng, sensor_rngs = rngs[0], rngs[1:]

    truth_objects = build_truth_objects(scenario, truth_rng)

    detections_by_sensor = {
        sensor.sensor_id: generate_sensor_detections(sensor, scenario, truth_objects, sensor_rng)
        for sensor, sensor_rng in zip(sensors, sensor_rngs, strict=True)
    }

    return SimulationResult(truth_objects=truth_objects, detections_by_sensor=detections_by_sensor)
