"""YAML config loading for scenario and sensor configs (architecture.md §2)."""

from __future__ import annotations

from pathlib import Path

import yaml

from src.config.models import ScenarioConfig, SensorConfig


def load_scenario_config(path: str | Path) -> ScenarioConfig:
    """Load and validate a scenario YAML file into a ``ScenarioConfig``."""
    return ScenarioConfig(**_read_yaml(path))


def load_sensor_config(path: str | Path) -> SensorConfig:
    """Load and validate a sensor YAML file into a ``SensorConfig``."""
    return SensorConfig(**_read_yaml(path))


def _read_yaml(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping at the top level in {path}")
    return data
