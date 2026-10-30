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
from src.adapters.messages import Detection
from src.config.models import DefendedArea, ScenarioConfig, SensorConfig
from src.simulator.detections import generate_sensor_detections
from src.simulator.rng import get_rng
from src.simulator.trajectories import TruthObject, TruthSample

AREA = DefendedArea(center_lat=38.8895, center_lon=-77.0353, radius_m=2000)
SCENARIO = ScenarioConfig(
    name="t", seed=1, duration_s=2, start_utc=1700000000.0, defended_area=AREA
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
