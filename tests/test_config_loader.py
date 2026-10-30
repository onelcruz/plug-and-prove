from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config.loader import load_scenario_config, load_sensor_config
from src.config.models import DefendedArea, ScenarioConfig, SensorConfig

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
