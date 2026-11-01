from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config.loader import load_scenario_config, load_sensor_config
from src.config.models import (
    BirdTarget,
    ClutterConfig,
    DefendedArea,
    DroneTarget,
    ScenarioConfig,
    SensorConfig,
)

CONFIG_ROOT = Path(__file__).resolve().parent.parent / "config"


def test_load_scenario_config():
    cfg = load_scenario_config(CONFIG_ROOT / "scenarios" / "example_scenario.yaml")
    assert cfg.name == "baseline-demo"
    assert cfg.seed == 42
    assert cfg.defended_area.center_lat == 38.8895
    assert cfg.defended_area.radius_m == 2000


def test_load_sensor_config():
    cfg = load_sensor_config(CONFIG_ROOT / "sensors" / "example_sensor.yaml")
    assert cfg.sensor_id == "sensor-1"
    assert cfg.accuracy_m == 15.0
    assert 0.0 <= cfg.dropout_probability <= 1.0


def test_defended_area_rejects_out_of_range_latitude(tmp_path):
    bad_config = tmp_path / "bad_scenario.yaml"
    bad_config.write_text(
        "name: bad\nseed: 1\ndefended_area:\n  center_lat: 999\n  center_lon: 0\n  radius_m: 10\n"
    )
    with pytest.raises(ValidationError):
        load_scenario_config(bad_config)


def _sensor_kwargs(**overrides):
    kwargs = dict(
        sensor_id="s",
        accuracy_m=10.0,
        range_m=5000.0,
        update_rate_hz=2.0,
        dropout_probability=0.0,
        heartbeat_timeout_s=1.0,
        min_hz=1.0,
        max_hz=4.0,
        max_accuracy_m=50.0,
    )
    kwargs.update(overrides)
    return kwargs


def test_heartbeat_timeout_s_above_tick_interval_is_accepted():
    # update_rate_hz=2.0 -> min_interval_s=0.5; 0.5 + epsilon must pass.
    cfg = SensorConfig(**_sensor_kwargs(heartbeat_timeout_s=0.500001))
    assert cfg.heartbeat_timeout_s == 0.500001


def test_heartbeat_timeout_s_rejects_exact_tick_interval_boundary():
    # Strict ">" per the model's docstring: exactly equal to 1/update_rate_hz must raise.
    with pytest.raises(ValidationError, match="heartbeat_timeout_s"):
        SensorConfig(**_sensor_kwargs(heartbeat_timeout_s=0.5))


def test_heartbeat_timeout_s_rejects_below_tick_interval():
    with pytest.raises(ValidationError, match="heartbeat_timeout_s"):
        SensorConfig(**_sensor_kwargs(heartbeat_timeout_s=0.1))


def _scenario_kwargs(**overrides):
    kwargs = dict(
        name="t",
        seed=1,
        duration_s=2.0,
        start_utc=1700000000.0,
        defended_area=DefendedArea(center_lat=0.0, center_lon=0.0, radius_m=10.0),
        max_clock_offset_s=0.5,
        min_alt_m=0.0,
        max_alt_m=200.0,
    )
    kwargs.update(overrides)
    return kwargs


def test_scenario_config_requires_start_utc():
    kwargs = _scenario_kwargs()
    del kwargs["start_utc"]
    with pytest.raises(ValidationError, match="start_utc"):
        ScenarioConfig(**kwargs)


def test_scenario_config_rejects_negative_start_utc():
    with pytest.raises(ValidationError, match="start_utc"):
        ScenarioConfig(**_scenario_kwargs(start_utc=-1.0))


def test_example_yamls_load_with_conformance_limits():
    sensor_1 = load_sensor_config(CONFIG_ROOT / "sensors" / "example_sensor.yaml")
    sensor_2 = load_sensor_config(CONFIG_ROOT / "sensors" / "sensor_2.yaml")
    scenario = load_scenario_config(CONFIG_ROOT / "scenarios" / "example_scenario.yaml")
    assert (sensor_1.min_hz, sensor_1.max_hz, sensor_1.max_accuracy_m) == (1.5, 2.5, 50.0)
    assert (sensor_2.min_hz, sensor_2.max_hz, sensor_2.max_accuracy_m) == (4.0, 6.0, 50.0)
    assert (scenario.max_clock_offset_s, scenario.min_alt_m, scenario.max_alt_m) == (
        0.5,
        0.0,
        200.0,
    )


def test_sensor_rejects_min_hz_above_update_rate():
    with pytest.raises(ValidationError, match=r"min_hz \(2.5\).*update_rate_hz \(2.0\)"):
        SensorConfig(**_sensor_kwargs(min_hz=2.5))


def test_sensor_rejects_update_rate_above_max_hz():
    with pytest.raises(ValidationError, match=r"update_rate_hz \(2.0\).*max_hz \(1.5\)"):
        SensorConfig(**_sensor_kwargs(min_hz=1.0, max_hz=1.5))


def test_sensor_rejects_accuracy_above_max_accuracy():
    with pytest.raises(ValidationError, match=r"accuracy_m \(10.0\).*max_accuracy_m \(9.0\)"):
        SensorConfig(**_sensor_kwargs(max_accuracy_m=9.0))


def test_sensor_accepts_boundary_equal_limits():
    cfg = SensorConfig(**_sensor_kwargs(min_hz=2.0, max_hz=2.0, max_accuracy_m=10.0))
    assert cfg.min_hz == cfg.update_rate_hz == cfg.max_hz


@pytest.mark.parametrize("field", ["max_clock_offset_s", "min_alt_m", "max_alt_m"])
def test_scenario_requires_conformance_limits(field):
    kwargs = _scenario_kwargs()
    del kwargs[field]
    with pytest.raises(ValidationError, match=field):
        ScenarioConfig(**kwargs)


def test_scenario_rejects_min_alt_not_below_max_alt():
    with pytest.raises(ValidationError, match=r"min_alt_m \(100.0\).*max_alt_m \(100.0\)"):
        ScenarioConfig(**_scenario_kwargs(min_alt_m=100.0, max_alt_m=100.0))


def _drone(altitude_m: float) -> DroneTarget:
    return DroneTarget(
        target_id="d",
        start_bearing_deg=0.0,
        start_range_m=1000.0,
        speed_mps=10.0,
        altitude_m=altitude_m,
    )


def _bird(altitude_m: float) -> BirdTarget:
    return BirdTarget(
        target_id="b", start_lat=0.0, start_lon=0.0, speed_mps=5.0, altitude_m=altitude_m
    )


@pytest.mark.parametrize(
    ("overrides", "label"),
    [
        (lambda: {"drones": [_drone(201.0)]}, "drone 'd'"),
        (lambda: {"birds": [_bird(201.0)]}, "bird 'b'"),
        (lambda: {"clutter": ClutterConfig(count=1, altitude_m=201.0)}, "clutter"),
        (lambda: {"drones": [_drone(5.0)], "min_alt_m": 10.0}, "drone 'd'"),
    ],
)
def test_scenario_rejects_target_altitude_outside_bounds(overrides, label):
    with pytest.raises(ValidationError, match=f"{label} altitude_m"):
        ScenarioConfig(**_scenario_kwargs(**overrides()))


def test_scenario_accepts_target_altitude_on_bounds():
    cfg = ScenarioConfig(
        **_scenario_kwargs(
            drones=[_drone(200.0)], birds=[_bird(10.0)], min_alt_m=10.0, max_alt_m=200.0
        )
    )
    assert cfg.drones[0].altitude_m == cfg.max_alt_m
    assert cfg.birds[0].altitude_m == cfg.min_alt_m
