"""Tests for the sensor adapter contract (issue #6): Detection-path behavior.

Covers schema conformance, unit correctness, and the FR-009/FR-010/FR-011
contract-violation behaviors for both concrete adapters. Heartbeat/schedule-
coverage tests live in a separate test class added for User Story 3
(disposition: tests/test_adapters.py is shared across US1 and US3, per
tasks.md T015's note to land sequentially in the same file).
"""

from src.adapters import sensor1, sensor2
from src.adapters.base import translate
from src.adapters.messages import Detection
from src.config.models import DefendedArea, ScenarioConfig, SensorConfig
from src.simulator.detections import RawDetection, generate_sensor_detections
from src.simulator.rng import get_rng
from src.simulator.trajectories import TruthObject, TruthSample

AREA = DefendedArea(center_lat=38.8895, center_lon=-77.0353, radius_m=2000)
SCENARIO = ScenarioConfig(
    name="t", seed=1, duration_s=2, start_utc=1700000000.0, defended_area=AREA
)


def _stationary_object(lat: float, lon: float, alt_m: float = 100.0) -> TruthObject:
    return TruthObject(
        object_id="obj-1",
        kind="drone",
        samples=(
            TruthSample(t_s=0.0, lat=lat, lon=lon, alt_m=alt_m),
            TruthSample(t_s=2.0, lat=lat, lon=lon, alt_m=alt_m),
        ),
    )


def test_both_adapters_produce_valid_detections():
    obj = _stationary_object(38.8895, -77.0353)
    for config in (sensor1.sensor_config, sensor2.sensor_config):
        raw = generate_sensor_detections(config, SCENARIO, [obj], get_rng(1))
        detections = translate(raw, config, SCENARIO)
        assert len(detections) == len(raw) > 0
        assert all(isinstance(d, Detection) for d in detections)


def test_optional_fields_none_when_absent_from_raw():
    obj = _stationary_object(38.8895, -77.0353)
    raw = generate_sensor_detections(sensor1.sensor_config, SCENARIO, [obj], get_rng(1))
    detections = translate(raw, sensor1.sensor_config, SCENARIO)
    assert all(d.velocity_mps is None and d.confidence is None for d in detections)


def test_timestamp_utc_derived_from_start_utc_plus_t_s():
    obj = _stationary_object(38.8895, -77.0353)
    raw = generate_sensor_detections(sensor1.sensor_config, SCENARIO, [obj], get_rng(1))
    detections = translate(raw, sensor1.sensor_config, SCENARIO)
    for d, r in zip(detections, raw, strict=True):
        assert d.timestamp_utc == SCENARIO.start_utc + r.t_s


def test_detection_id_unique_across_simultaneous_same_tick_detections():
    # Two distinct, co-located truth objects guarantee >1 detection at tick 0.
    sensor = SensorConfig(
        sensor_id="multi",
        accuracy_m=5,
        range_m=5000,
        update_rate_hz=1,
        dropout_probability=0.0,
        heartbeat_timeout_s=5.0,
    )
    obj_a = TruthObject(
        object_id="a",
        kind="drone",
        samples=(TruthSample(t_s=0.0, lat=38.8895, lon=-77.0353, alt_m=100.0),),
    )
    obj_b = TruthObject(
        object_id="b",
        kind="drone",
        samples=(TruthSample(t_s=0.0, lat=38.8896, lon=-77.0354, alt_m=100.0),),
    )
    raw = generate_sensor_detections(sensor, SCENARIO, [obj_a, obj_b], get_rng(1))
    assert len(raw) == 2
    detections = translate(raw, sensor, SCENARIO)
    ids = [d.detection_id for d in detections]
    assert len(ids) == len(set(ids))
    assert ids == ["multi:0:0", "multi:0:1"]


def test_off_schedule_t_s_raises():
    bad_raw = RawDetection(
        sensor_id=sensor1.sensor_config.sensor_id,
        t_s=0.123456,
        lat=38.8895,
        lon=-77.0353,
        alt_m=100.0,
        accuracy_m=10.0,
    )
    try:
        translate([bad_raw], sensor1.sensor_config, SCENARIO)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for off-schedule t_s")


def test_mismatched_sensor_id_raises():
    bad_raw = RawDetection(
        sensor_id="not-sensor-1",
        t_s=0.0,
        lat=38.8895,
        lon=-77.0353,
        alt_m=100.0,
        accuracy_m=10.0,
    )
    try:
        translate([bad_raw], sensor1.sensor_config, SCENARIO)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for mismatched sensor_id")
