from src.config.models import DefendedArea, ScenarioConfig, SensorConfig
from src.simulator.detections import generate_sensor_detections
from src.simulator.rng import get_rng
from src.simulator.trajectories import TruthObject, TruthSample

AREA = DefendedArea(center_lat=0.0, center_lon=0.0, radius_m=2000)
SCENARIO = ScenarioConfig(
    name="t",
    seed=1,
    duration_s=10,
    start_utc=1700000000.0,
    defended_area=AREA,
    max_clock_offset_s=0.5,
    min_alt_m=0.0,
    max_alt_m=200.0,
)


def _stationary_object(lat: float, lon: float, alt_m: float = 100.0) -> TruthObject:
    return TruthObject(
        object_id="obj-1",
        kind="drone",
        samples=(
            TruthSample(t_s=0.0, lat=lat, lon=lon, alt_m=alt_m),
            TruthSample(t_s=10.0, lat=lat, lon=lon, alt_m=alt_m),
        ),
    )


def test_reproducible_detections():
    sensor = SensorConfig(
        sensor_id="s1",
        accuracy_m=10,
        range_m=5000,
        update_rate_hz=2,
        dropout_probability=0.1,
        heartbeat_timeout_s=10.0,
        min_hz=0.5,
        max_hz=10.0,
        max_accuracy_m=1000.0,
    )
    obj = _stationary_object(0.001, 0.001)
    a = generate_sensor_detections(sensor, SCENARIO, [obj], get_rng(5))
    b = generate_sensor_detections(sensor, SCENARIO, [obj], get_rng(5))
    assert a == b


def test_range_limit_cutoff():
    # ~111m per 0.001 degree of latitude near the equator.
    obj = _stationary_object(0.02, 0.0)  # ~2220m from sensor at (0, 0)
    near_sensor = SensorConfig(
        sensor_id="near",
        accuracy_m=1,
        range_m=5000,
        update_rate_hz=1,
        dropout_probability=0.0,
        heartbeat_timeout_s=10.0,
        min_hz=0.5,
        max_hz=10.0,
        max_accuracy_m=1000.0,
    )
    far_sensor = SensorConfig(
        sensor_id="far",
        accuracy_m=1,
        range_m=1000,
        update_rate_hz=1,
        dropout_probability=0.0,
        heartbeat_timeout_s=10.0,
        min_hz=0.5,
        max_hz=10.0,
        max_accuracy_m=1000.0,
    )
    in_range = generate_sensor_detections(near_sensor, SCENARIO, [obj], get_rng(1))
    out_of_range = generate_sensor_detections(far_sensor, SCENARIO, [obj], get_rng(1))
    assert len(in_range) > 0
    assert len(out_of_range) == 0


def test_dropout_always_drops_at_probability_one():
    obj = _stationary_object(0.001, 0.001)
    sensor = SensorConfig(
        sensor_id="s1",
        accuracy_m=1,
        range_m=5000,
        update_rate_hz=5,
        dropout_probability=1.0,
        heartbeat_timeout_s=10.0,
        min_hz=0.5,
        max_hz=10.0,
        max_accuracy_m=1000.0,
    )
    detections = generate_sensor_detections(sensor, SCENARIO, [obj], get_rng(1))
    assert detections == []


def test_tick_count_exact_for_non_binary_exact_rate():
    # Regression test (caught in independent code review of #5): 7 Hz over a
    # 10s duration has a non-exact-binary dt (1/7), which previously caused
    # float accumulation drift (`t_s += dt_s` repeatedly) to silently skip the
    # final in-spec tick. Tick-index-based computation must not drop it.
    obj = _stationary_object(0.001, 0.001)
    sensor = SensorConfig(
        sensor_id="s1",
        accuracy_m=1,
        range_m=5000,
        update_rate_hz=7,
        dropout_probability=0.0,
        heartbeat_timeout_s=10.0,
        min_hz=0.5,
        max_hz=10.0,
        max_accuracy_m=1000.0,
    )
    detections = generate_sensor_detections(sensor, SCENARIO, [obj], get_rng(1))
    # floor(10 / (1/7)) + 1 = floor(70) + 1 = 71 ticks, inclusive of t=0 and t=10.
    assert len(detections) == 71
    assert detections[-1].t_s == 10.0


def test_dropout_never_drops_at_probability_zero():
    obj = _stationary_object(0.001, 0.001)
    sensor = SensorConfig(
        sensor_id="s1",
        accuracy_m=1,
        range_m=5000,
        update_rate_hz=2,
        dropout_probability=0.0,
        heartbeat_timeout_s=10.0,
        min_hz=0.5,
        max_hz=10.0,
        max_accuracy_m=1000.0,
    )
    detections = generate_sensor_detections(sensor, SCENARIO, [obj], get_rng(1))
    # update_rate_hz=2 over duration_s=10 -> ticks at 0, 0.5, ..., 10 inclusive = 21 ticks.
    assert len(detections) == 21


def test_accuracy_affects_noise_magnitude():
    obj = _stationary_object(0.001, 0.001)
    tight_sensor = SensorConfig(
        sensor_id="tight",
        accuracy_m=0.01,
        range_m=5000,
        update_rate_hz=1,
        dropout_probability=0.0,
        heartbeat_timeout_s=10.0,
        min_hz=0.5,
        max_hz=10.0,
        max_accuracy_m=1000.0,
    )
    loose_sensor = SensorConfig(
        sensor_id="loose",
        accuracy_m=500,
        range_m=5000,
        update_rate_hz=1,
        dropout_probability=0.0,
        heartbeat_timeout_s=10.0,
        min_hz=0.5,
        max_hz=10.0,
        max_accuracy_m=1000.0,
    )
    tight = generate_sensor_detections(tight_sensor, SCENARIO, [obj], get_rng(9))
    loose = generate_sensor_detections(loose_sensor, SCENARIO, [obj], get_rng(9))
    tight_spread = max(abs(d.lat - 0.001) for d in tight)
    loose_spread = max(abs(d.lat - 0.001) for d in loose)
    assert loose_spread > tight_spread
