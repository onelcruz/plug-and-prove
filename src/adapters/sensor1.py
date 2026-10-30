"""Sensor 1's adapter: pairs the shared ``translate()`` with sensor 1's config.

Not a separate implementation -- re-exports ``base.translate`` directly, so
there is exactly one translation implementation shared by every sensor
(disposition item 30). This module exists only so #13's orchestration has a
name to import for sensor 1 specifically.
"""

from __future__ import annotations

from pathlib import Path

from src.adapters.base import translate
from src.config.loader import load_sensor_config

SENSOR_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "sensors" / "example_sensor.yaml"
)

sensor_config = load_sensor_config(SENSOR_CONFIG_PATH)

__all__ = ["translate", "sensor_config"]
