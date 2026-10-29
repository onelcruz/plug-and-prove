from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config.loader import load_scenario_config, load_sensor_config

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
