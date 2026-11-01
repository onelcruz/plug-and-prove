"""Sensor 3's adapter: the demo's injected clock-offset bug, and its fix (issue #8).

Sensor 3 reports GPS time, not UTC. GPS time is ahead of UTC by the accumulated
leap seconds (18 s since 2017-01-01). The module exports two ``SensorAdapter``
callables over the shared ``base.translate``:

- ``translate_with_clock_bug`` labels the sensor's GPS clock reading as UTC, so
  every message is 18 s ahead and the conformance harness blocks the sensor on
  check 4 (clock offset) alone.
- ``translate`` reports UTC, so its output equals ``base.translate``'s and the
  sensor passes all 7 checks.

The demo's "toggle" is which callable is submitted to the gate; wiring that
choice into a run is #13's job. The fix is adapter code: no scenario limit
(``max_clock_offset_s``) and no config field changes.
"""

from __future__ import annotations

from pathlib import Path

from src.adapters import base
from src.adapters.messages import Detection, Heartbeat
from src.config.loader import load_sensor_config
from src.config.models import ScenarioConfig, SensorConfig
from src.simulator.detections import RawDetection

SENSOR_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "sensors" / "sensor_3.yaml"

sensor_config = load_sensor_config(SENSOR_CONFIG_PATH)

# GPS time - UTC, in seconds: 18 s since 2017-01-01 (IERS Bulletin C 52).
# Must stay strictly greater than the scenario's max_clock_offset_s, or the
# demo bug would no longer fail the harness.
GPS_UTC_OFFSET_S = 18.0


def _gps_clock(
    raw_detections: list[RawDetection],
    sensor: SensorConfig,
    scenario: ScenarioConfig,
) -> list[Detection | Heartbeat]:
    """The shared translation, stamped with the sensor's GPS clock reading (UTC + 18 s)."""
    return [
        message.model_copy(update={"timestamp_utc": message.timestamp_utc + GPS_UTC_OFFSET_S})
        for message in base.translate(raw_detections, sensor, scenario)
    ]


def translate_with_clock_bug(
    raw_detections: list[RawDetection],
    sensor: SensorConfig,
    scenario: ScenarioConfig,
) -> list[Detection | Heartbeat]:
    """The demo bug: the GPS clock reading is labelled as UTC, so every timestamp is 18 s ahead."""
    return _gps_clock(raw_detections, sensor, scenario)


def translate(
    raw_detections: list[RawDetection],
    sensor: SensorConfig,
    scenario: ScenarioConfig,
) -> list[Detection | Heartbeat]:
    """The fix: report UTC, i.e. remove the 18 s that the bug adds (GPS - UTC).

    UTC is taken straight from the shared translation rather than recovered as
    ``(utc + GPS_UTC_OFFSET_S) - GPS_UTC_OFFSET_S``: that round trip is not exact
    where adding 18 s crosses a float64 binade (e.g. just below 2**30 or 2**31 s).
    """
    return base.translate(raw_detections, sensor, scenario)


__all__ = ["GPS_UTC_OFFSET_S", "translate", "translate_with_clock_bug", "sensor_config"]
