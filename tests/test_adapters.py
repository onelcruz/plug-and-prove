"""Tests for the sensor adapter contract (issue #6): Detection-path behavior.

Covers schema conformance, unit correctness, and the FR-009/FR-010/FR-011
contract-violation behaviors for both concrete adapters. Heartbeat/schedule-
coverage tests live in a separate test class added for User Story 3
(disposition: tests/test_adapters.py is shared across US1 and US3, per
tasks.md T015's note to land sequentially in the same file).
"""

import pytest

from src.adapters import sensor1, sensor2
from src.adapters.base import translate
from src.adapters.messages import Detection, Heartbeat
from src.config.models import DefendedArea, ScenarioConfig, SensorConfig
from src.simulator.detections import RawDetection, expected_ticks, generate_sensor_detections
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
        messages = translate(raw, config, SCENARIO)
        # Full coverage: every scheduled tick produced exactly one message.
        assert len(messages) == len(expected_ticks(config.update_rate_hz, SCENARIO.duration_s))
        detections = [m for m in messages if isinstance(m, Detection)]
        assert len(detections) == len(raw) > 0
        assert all(isinstance(m, Detection | Heartbeat) for m in messages)


def test_optional_fields_none_when_absent_from_raw():
    obj = _stationary_object(38.8895, -77.0353)
    raw = generate_sensor_detections(sensor1.sensor_config, SCENARIO, [obj], get_rng(1))
    messages = translate(raw, sensor1.sensor_config, SCENARIO)
    detections = [m for m in messages if isinstance(m, Detection)]
    assert len(detections) > 0
    assert all(d.velocity_mps is None and d.confidence is None for d in detections)


def test_timestamp_utc_derived_from_start_utc_plus_t_s():
    obj = _stationary_object(38.8895, -77.0353)
    raw = generate_sensor_detections(sensor1.sensor_config, SCENARIO, [obj], get_rng(1))
    messages = translate(raw, sensor1.sensor_config, SCENARIO)
    detections = [m for m in messages if isinstance(m, Detection)]
    assert len(detections) == len(raw)
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
    messages = translate(raw, sensor, SCENARIO)
    detections = [m for m in messages if isinstance(m, Detection)]
    ids = [d.detection_id for d in detections]
    assert len(ids) == len(set(ids))
    assert ids == ["multi:0:0", "multi:0:1"]


def test_detection_id_uses_schedule_tick_index_not_detection_order():
    """FR-009: detection_id's tick_index is the scheduled-tick index, not a
    counter over detections only -- a detection landing after Heartbeat ticks
    must still carry its true schedule position."""
    sensor = SensorConfig(
        sensor_id="multi",
        accuracy_m=5,
        range_m=5000,
        update_rate_hz=1,
        dropout_probability=0.0,
        heartbeat_timeout_s=5.0,
    )
    # Object only appears at t_s=2.0, so ticks 0 and 1 (of a 2s/1Hz schedule:
    # 0,1,2) must be Heartbeat, and the single Detection must be "multi:2:0".
    obj = TruthObject(
        object_id="a",
        kind="drone",
        samples=(TruthSample(t_s=2.0, lat=38.8895, lon=-77.0353, alt_m=100.0),),
    )
    raw = generate_sensor_detections(sensor, SCENARIO, [obj], get_rng(1))
    messages = translate(raw, sensor, SCENARIO)
    assert [type(m) for m in messages] == [Heartbeat, Heartbeat, Detection]
    assert messages[2].detection_id == "multi:2:0"


def test_off_schedule_t_s_raises():
    bad_raw = RawDetection(
        sensor_id=sensor1.sensor_config.sensor_id,
        t_s=0.123456,
        lat=38.8895,
        lon=-77.0353,
        alt_m=100.0,
        accuracy_m=10.0,
    )
    with pytest.raises(ValueError, match="scheduled tick"):
        translate([bad_raw], sensor1.sensor_config, SCENARIO)


def test_near_miss_t_s_raises_not_silently_rounded():
    """FR-010: a t_s that is a near-float-miss of a real scheduled tick (not
    just a wildly off value) must still raise, not be silently accepted."""
    ticks = expected_ticks(sensor1.sensor_config.update_rate_hz, SCENARIO.duration_s)
    near_miss = ticks[1] + 1e-6
    bad_raw = RawDetection(
        sensor_id=sensor1.sensor_config.sensor_id,
        t_s=near_miss,
        lat=38.8895,
        lon=-77.0353,
        alt_m=100.0,
        accuracy_m=10.0,
    )
    with pytest.raises(ValueError, match="scheduled tick"):
        translate([bad_raw], sensor1.sensor_config, SCENARIO)


def test_off_schedule_raise_also_triggers_amid_otherwise_valid_batch():
    """A bad item after valid ones in the same batch must still raise (FR-010),
    not be masked by earlier successful Detection construction."""
    good_raw = RawDetection(
        sensor_id=sensor1.sensor_config.sensor_id,
        t_s=0.0,
        lat=38.8895,
        lon=-77.0353,
        alt_m=100.0,
        accuracy_m=10.0,
    )
    bad_raw = RawDetection(
        sensor_id=sensor1.sensor_config.sensor_id,
        t_s=0.123456,
        lat=38.8895,
        lon=-77.0353,
        alt_m=100.0,
        accuracy_m=10.0,
    )
    with pytest.raises(ValueError, match="scheduled tick"):
        translate([good_raw, bad_raw], sensor1.sensor_config, SCENARIO)


def test_mismatched_sensor_id_raises():
    bad_raw = RawDetection(
        sensor_id="not-sensor-1",
        t_s=0.0,
        lat=38.8895,
        lon=-77.0353,
        alt_m=100.0,
        accuracy_m=10.0,
    )
    with pytest.raises(ValueError, match="does not match"):
        translate([bad_raw], sensor1.sensor_config, SCENARIO)


# --- User Story 3: Heartbeat / schedule-coverage (FR-006, SC-003) -----------


def test_every_scheduled_tick_yields_exactly_one_message():
    """SC-003: every scheduled tick is accounted for as Detection or Heartbeat."""
    sensor = SensorConfig(
        sensor_id="multi",
        accuracy_m=5,
        range_m=5000,
        update_rate_hz=1,
        dropout_probability=0.0,
        heartbeat_timeout_s=5.0,
    )
    # Truth object only exists for t_s in [0.0, 1.0], so tick 2.0 (of 0,1,2) has
    # no target in range and must yield a Heartbeat, not a missing entry.
    obj = TruthObject(
        object_id="a",
        kind="drone",
        samples=(
            TruthSample(t_s=0.0, lat=38.8895, lon=-77.0353, alt_m=100.0),
            TruthSample(t_s=1.0, lat=38.8895, lon=-77.0353, alt_m=100.0),
        ),
    )
    raw = generate_sensor_detections(sensor, SCENARIO, [obj], get_rng(1))
    messages = translate(raw, sensor, SCENARIO)
    ticks = expected_ticks(sensor.update_rate_hz, SCENARIO.duration_s)
    assert len(messages) == len(ticks) == 3
    assert [type(m) for m in messages] == [Detection, Detection, Heartbeat]


def test_heartbeat_emitted_for_every_tick_when_no_targets_in_view():
    sensor = SensorConfig(
        sensor_id="multi",
        accuracy_m=5,
        range_m=5000,
        update_rate_hz=1,
        dropout_probability=0.0,
        heartbeat_timeout_s=5.0,
    )
    raw = generate_sensor_detections(sensor, SCENARIO, [], get_rng(1))
    assert raw == []
    messages = translate(raw, sensor, SCENARIO)
    ticks = expected_ticks(sensor.update_rate_hz, SCENARIO.duration_s)
    assert len(messages) == len(ticks) > 0
    assert all(isinstance(m, Heartbeat) for m in messages)


def test_heartbeat_shares_detection_time_base():
    sensor = SensorConfig(
        sensor_id="multi",
        accuracy_m=5,
        range_m=5000,
        update_rate_hz=1,
        dropout_probability=0.0,
        heartbeat_timeout_s=5.0,
    )
    messages = translate([], sensor, SCENARIO)
    for m in messages:
        assert isinstance(m, Heartbeat)
        assert m.timestamp_utc == SCENARIO.start_utc + m.t_s
        assert m.sensor_id == sensor.sensor_id


def test_both_concrete_adapters_emit_heartbeats_once_target_leaves_view():
    """SC-004: heartbeat coverage exercised through sensor1/sensor2's real configs
    (real update_rate_hz, dropout_probability), not just an ad-hoc test sensor."""
    # Object is only tracked for t_s in [0.0, 1.0] of this 2s scenario, so every
    # tick after 1.0 has no target in range and must yield a Heartbeat.
    obj = TruthObject(
        object_id="obj-1",
        kind="drone",
        samples=(
            TruthSample(t_s=0.0, lat=38.8895, lon=-77.0353, alt_m=100.0),
            TruthSample(t_s=1.0, lat=38.8895, lon=-77.0353, alt_m=100.0),
        ),
    )
    for config in (sensor1.sensor_config, sensor2.sensor_config):
        raw = generate_sensor_detections(config, SCENARIO, [obj], get_rng(1))
        messages = translate(raw, config, SCENARIO)
        ticks = expected_ticks(config.update_rate_hz, SCENARIO.duration_s)
        assert len(messages) == len(ticks)
        # Honors this sensor's own schedule (2Hz for sensor-1, 5Hz for sensor-2),
        # not a shared/copy-pasted rate (FR-004).
        late_heartbeats = [
            m
            for t_s, m in zip(ticks, messages, strict=True)
            if t_s > 1.0 and isinstance(m, Heartbeat)
        ]
        assert len(late_heartbeats) > 0
        for hb in late_heartbeats:
            assert hb.sensor_id == config.sensor_id
            assert hb.timestamp_utc == SCENARIO.start_utc + hb.t_s
