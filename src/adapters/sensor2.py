"""Sensor 2's adapter: pairs the shared ``translate()`` with sensor 2's config.

Not a separate implementation -- re-exports ``base.translate`` directly, same
as ``sensor1.py``; the two sensors differ only in which ``SensorConfig`` each
module pairs it with (disposition item 30).
"""

from __future__ import annotations

from pathlib import Path

from src.adapters.base import translate
from src.config.loader import load_sensor_config

SENSOR_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "sensors" / "sensor_2.yaml"

sensor_config = load_sensor_config(SENSOR_CONFIG_PATH)

__all__ = ["translate", "sensor_config"]
