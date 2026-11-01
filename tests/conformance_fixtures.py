"""Shared fixtures for the conformance harness tests: configs, real streams, faulty adapters."""

from __future__ import annotations

from functools import cache
from pathlib import Path

from src.adapters import sensor1, sensor2
from src.adapters.base import translate
from src.adapters.messages import Detection, Heartbeat
from src.config.loader import load_scenario_config
from src.config.models import ScenarioConfig, SensorConfig
from src.simulator.detections import RawDetection
from src.simulator.scenario import run_simulation

CONFIG_ROOT = Path(__file__).resolve().parent.parent / "config"
SCENARIO = load_scenario_config(CONFIG_ROOT / "scenarios" / "example_scenario.yaml")
SENSORS = (sensor1.sensor_config, sensor2.sensor_config)
CLOCK_OFFSET_S = 2.0


@cache
def real_streams() -> dict[str, list[RawDetection]]:
    """Raw detections per sensor from the example scenario (deterministic: seeded)."""
    return run_simulation(SCENARIO, list(SENSORS)).detections_by_sensor


def offset_adapter(raw, sensor: SensorConfig, scenario: ScenarioConfig):
    """A faulty adapter: ``base.translate`` plus a constant +2.0 s clock offset on every message."""
    return [
        m.model_copy(update={"timestamp_utc": m.timestamp_utc + CLOCK_OFFSET_S})
        for m in translate(raw, sensor, scenario)
    ]


def feet_adapter(raw, sensor: SensorConfig, scenario: ScenarioConfig):
    """A faulty adapter that reports altitude in feet instead of meters."""
    return [
        m.model_copy(update={"alt_m": m.alt_m * 3.28084}) if isinstance(m, Detection) else m
        for m in translate(raw, sensor, scenario)
    ]


def heartbeat_dropping_adapter(raw, sensor: SensorConfig, scenario: ScenarioConfig):
    """A faulty adapter that silently discards every Heartbeat."""
    return [m for m in translate(raw, sensor, scenario) if not isinstance(m, Heartbeat)]


def raising_adapter(raw, sensor: SensorConfig, scenario: ScenarioConfig):
    raise RuntimeError("boom\nsecond line")


def wrong_sensor_id_adapter(raw, sensor: SensorConfig, scenario: ScenarioConfig):
    """A faulty adapter that labels every message with another sensor's id (F5)."""
    return [
        m.model_copy(update={"sensor_id": "sensor-other"}) for m in translate(raw, sensor, scenario)
    ]


def duplicate_id_adapter(raw, sensor: SensorConfig, scenario: ScenarioConfig):
    """A faulty adapter whose detection_id uses the tick index alone (F6).

    Valid on a one-target-per-tick probe; collides whenever two real targets share a tick.
    """
    messages = []
    for m in translate(raw, sensor, scenario):
        if isinstance(m, Detection):
            tick = round((m.timestamp_utc - scenario.start_utc) * sensor.update_rate_hz)
            m = m.model_copy(update={"detection_id": f"{m.sensor_id}:{tick}"})
        messages.append(m)
    return messages


def replayed_heartbeat_adapter(raw, sensor: SensorConfig, scenario: ScenarioConfig):
    """A faulty adapter that replays its first Heartbeat for every Heartbeat it should emit (F3)."""
    messages = translate(raw, sensor, scenario)
    first = next((m for m in messages if isinstance(m, Heartbeat)), None)
    return [first if isinstance(m, Heartbeat) else m for m in messages]


def mutating_limit_adapter(raw, sensor: SensorConfig, scenario: ScenarioConfig):
    """A faulty adapter that loosens its own acceptance limit, then skews by 2 s (F4)."""
    scenario.max_clock_offset_s = 3.0
    return offset_adapter(raw, sensor, scenario)


def mutating_input_adapter(raw, sensor: SensorConfig, scenario: ScenarioConfig):
    """A faulty adapter that shifts the raw inputs' times, and its output with them (F4)."""
    messages = translate(raw, sensor, scenario)
    for r in raw:
        r.t_s += CLOCK_OFFSET_S
    return [
        m.model_copy(update={"timestamp_utc": m.timestamp_utc + CLOCK_OFFSET_S}) for m in messages
    ]


class StubFusion:
    """A stand-in downstream consumer: it only ever sees what the gate releases."""

    def __init__(self) -> None:
        self.received: list[Detection] = []

    def ingest(self, detections: list[Detection]) -> None:
        self.received.extend(detections)
