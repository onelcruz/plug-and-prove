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
from src.simulator.detections import RawDetection, expected_ticks


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


def translate(
    raw_detections: list[RawDetection],
    sensor: SensorConfig,
    scenario: ScenarioConfig,
) -> list[Detection | Heartbeat]:
    """Translate a sensor's raw detection stream into canonical pipeline messages.

    A pure, stateless, batch function: every scheduled tick (per
    ``expected_ticks``) either has a matching ``RawDetection`` -- translated
    into a ``Detection`` -- or does not, in which case a ``Heartbeat`` is
    emitted instead (FR-006), so every scheduled tick is accounted for in the
    output (SC-003). This proves schedule-coverage, not real sensor liveness/
    failure -- see specs/006-sensor-adapter-contract/plan.md's "Known
    limitation": ``translate`` has no way to observe whether the upstream
    feed was actually still being produced, only whether a tick's scheduled
    slot was filled.

    Raises ``ValueError`` if any ``raw.t_s`` is not exactly a value from
    ``expected_ticks(sensor.update_rate_hz, scenario.duration_s)`` (FR-010),
    or if any ``raw.sensor_id`` does not match ``sensor.sensor_id`` (FR-011)
    -- both are contract violations, not something to silently drop.
    """
    ticks = expected_ticks(sensor.update_rate_hz, scenario.duration_s)
    tick_index_by_t_s = {t_s: i for i, t_s in enumerate(ticks)}
    if len(tick_index_by_t_s) != len(ticks):
        raise AssertionError("expected_ticks() returned non-unique ticks")

    detections_by_tick: dict[int, list[Detection]] = {}

    for raw in raw_detections:
        if raw.sensor_id != sensor.sensor_id:
            raise ValueError(
                f"RawDetection.sensor_id {raw.sensor_id!r} does not match the adapter's "
                f"configured sensor_id {sensor.sensor_id!r}"
            )
        if raw.t_s not in tick_index_by_t_s:
            raise ValueError(
                f"RawDetection.t_s={raw.t_s} is not a scheduled tick for update_rate_hz="
                f"{sensor.update_rate_hz} over duration_s={scenario.duration_s}"
            )

        tick_index = tick_index_by_t_s[raw.t_s]
        bucket = detections_by_tick.setdefault(tick_index, [])
        index_within_tick = len(bucket)

        bucket.append(
            Detection(
                sensor_id=sensor.sensor_id,
                detection_id=f"{sensor.sensor_id}:{tick_index}:{index_within_tick}",
                timestamp_utc=scenario.start_utc + raw.t_s,
                lat=raw.lat,
                lon=raw.lon,
                alt_m=raw.alt_m,
                accuracy_m=sensor.accuracy_m,
                velocity_mps=None,
                confidence=None,
                raw_payload=raw.model_dump(),
            )
        )

    messages: list[Detection | Heartbeat] = []
    for tick_index, t_s in enumerate(ticks):
        bucket = detections_by_tick.get(tick_index)
        if bucket:
            messages.extend(bucket)
        else:
            messages.append(
                Heartbeat(
                    sensor_id=sensor.sensor_id,
                    timestamp_utc=scenario.start_utc + t_s,
                    t_s=t_s,
                )
            )

    return messages
