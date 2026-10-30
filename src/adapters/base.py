"""Sensor adapter contract: the ``SensorAdapter`` protocol and its one shared
implementation, ``translate()`` (architecture.md §3).

Concrete per-sensor adapters (``sensor1.py``, ``sensor2.py``) are thin modules
that re-export ``translate`` alongside their own sensor's ``SensorConfig`` --
``translate`` itself is sensor-agnostic and never duplicated. A new sensor is
added by implementing this same protocol plus a ``SensorConfig`` entry, with
zero changes to this module, ``src/simulator/``, or any other adapter (FR-005).
"""

from __future__ import annotations

from typing import Protocol

from src.adapters.messages import Detection, Heartbeat
from src.config.models import ScenarioConfig, SensorConfig
from src.simulator.detections import RawDetection


class SensorAdapter(Protocol):
    """The structural contract every adapter (present and future) implements.

    The harness and orchestrator interact with any adapter only through this
    interface -- never through a concrete adapter's internals (FR-002). The
    fusion engine never calls an adapter directly (FR-012).
    """

    def __call__(
        self,
        raw_detections: list[RawDetection],
        sensor: SensorConfig,
        scenario: ScenarioConfig,
    ) -> list[Detection | Heartbeat]: ...
