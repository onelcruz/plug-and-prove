"""Extensibility proof (User Story 2 / SC-002): a new sensor can be added by
implementing only the ``SensorAdapter`` interface plus a ``SensorConfig``
entry, with zero changes to ``src/simulator/``, the ``Detection``/``Heartbeat``
schemas, ``src/adapters/base.py``'s ``translate`` signature, or sensor 1/2's
adapters.

This throwaway test adapter is not a new file under ``src/adapters/`` --
it's a locally-constructed ``SensorConfig`` paired directly with the existing
``base.translate``, proving the shared implementation needs nothing sensor-
specific beyond config data it already accepts.
"""

from src.adapters.base import translate
from src.adapters.messages import Detection, Heartbeat
from src.config.models import DefendedArea, ScenarioConfig, SensorConfig
from src.simulator.detections import expected_ticks, generate_sensor_detections
from src.simulator.rng import get_rng
from src.simulator.trajectories import TruthObject, TruthSample

AREA = DefendedArea(center_lat=38.8895, center_lon=-77.0353, radius_m=2000)
SCENARIO = ScenarioConfig(
    name="t",
    seed=1,
    duration_s=2,
    start_utc=1700000000.0,
    defended_area=AREA,
    max_clock_offset_s=0.5,
    min_alt_m=0.0,
    max_alt_m=200.0,
)

# A throwaway "sensor 3" config -- no new src/adapters/ module, no changes
# anywhere else, just a new SensorConfig instance handed to the same
# base.translate every other adapter uses.
THROWAWAY_SENSOR = SensorConfig(
    sensor_id="sensor-3-test",
    accuracy_m=20.0,
    range_m=4000,
    update_rate_hz=3.0,
    dropout_probability=0.0,
    heartbeat_timeout_s=1.0,
    min_hz=0.5,
    max_hz=10.0,
    max_accuracy_m=1000.0,
)


def test_new_sensor_addable_via_sensor_adapter_alone():
    obj = TruthObject(
        object_id="obj-1",
        kind="drone",
        samples=(
            TruthSample(t_s=0.0, lat=38.8895, lon=-77.0353, alt_m=100.0),
            TruthSample(t_s=2.0, lat=38.8895, lon=-77.0353, alt_m=100.0),
        ),
    )
    raw = generate_sensor_detections(THROWAWAY_SENSOR, SCENARIO, [obj], get_rng(1))
    detections = translate(raw, THROWAWAY_SENSOR, SCENARIO)

    assert len(detections) == len(raw) > 0
    assert all(isinstance(d, Detection) for d in detections)
    assert all(d.sensor_id == THROWAWAY_SENSOR.sensor_id for d in detections)


def test_new_sensor_also_gets_heartbeat_and_detection_id_for_free():
    """The same zero-code-change guarantee extends to Heartbeat/detection_id --
    not just Detection schema conformance -- since translate() is entirely
    config-driven, not sensor-1/sensor-2-specific."""
    # Object only in view for t_s in [0.0, 1.0], so later ticks get Heartbeat.
    obj = TruthObject(
        object_id="obj-1",
        kind="drone",
        samples=(
            TruthSample(t_s=0.0, lat=38.8895, lon=-77.0353, alt_m=100.0),
            TruthSample(t_s=1.0, lat=38.8895, lon=-77.0353, alt_m=100.0),
        ),
    )
    raw = generate_sensor_detections(THROWAWAY_SENSOR, SCENARIO, [obj], get_rng(1))
    messages = translate(raw, THROWAWAY_SENSOR, SCENARIO)
    ticks = expected_ticks(THROWAWAY_SENSOR.update_rate_hz, SCENARIO.duration_s)

    assert len(messages) == len(ticks)
    assert any(isinstance(m, Heartbeat) for m in messages)
    for tick_index, message in enumerate(messages):
        if isinstance(message, Detection):
            assert message.detection_id == f"{THROWAWAY_SENSOR.sensor_id}:{tick_index}:0"
