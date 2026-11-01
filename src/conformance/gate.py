"""The conformance gate: the only path from an adapter's output to downstream consumers.

Architecture.md §12 row 3 locks that fusion only ever receives ``Detection``s from
adapters that passed the harness. ``Heartbeat``s are never released.
"""

from __future__ import annotations

from src.adapters.base import SensorAdapter
from src.adapters.messages import Detection
from src.config.models import ScenarioConfig, SensorConfig
from src.conformance.harness import run_harness
from src.conformance.results import HarnessResult
from src.simulator.detections import RawDetection


class ConformanceGate:
    """Holds the latest verdict, and the real-stream ``Detection``s from that run, per sensor."""

    def __init__(self) -> None:
        # A re-submit replaces a sensor's entry but keeps its original position.
        self._entries: dict[str, tuple[HarnessResult, list[Detection]]] = {}

    def submit(
        self,
        adapter: SensorAdapter,
        sensor: SensorConfig,
        scenario: ScenarioConfig,
        real_raw: list[RawDetection],
    ) -> HarnessResult:
        """Run the harness and record its verdict, replacing any earlier one for this sensor."""
        run = run_harness(adapter, sensor, scenario, real_raw)
        self._entries[sensor.sensor_id] = (run.result, run.real_detections)
        return run.result

    def admitted_detections(self, sensor_id: str) -> list[Detection]:
        """The sensor's real-stream ``Detection``s; ``[]`` unless its latest verdict is admitted."""
        entry = self._entries.get(sensor_id)
        if entry is None or not entry[0].admitted:
            return []
        return list(entry[1])

    def results(self) -> list[HarnessResult]:
        """The latest verdict per sensor, in the order sensors were first submitted."""
        return [result for result, _ in self._entries.values()]
