# Contract: `src/adapters/sensor3.py`

The public surface of sensor 3's adapter module. Both callables satisfy the unchanged #6
`SensorAdapter` protocol:

```text
(raw_detections: list[RawDetection], sensor: SensorConfig, scenario: ScenarioConfig)
    -> list[Detection | Heartbeat]
```

| Name | Kind | Contract |
|---|---|---|
| `GPS_UTC_OFFSET_S` | `float` constant = 18.0 | GPS − UTC. The comment cites the leap-second source. |
| `translate_with_clock_bug` | `SensorAdapter` | Same messages, order and fields as `base.translate`, except every `timestamp_utc` is `+ GPS_UTC_OFFSET_S`. Raises exactly what `base.translate` raises. Does not mutate its inputs. |
| `translate` | `SensorAdapter` | Output `==` `base.translate(raw, sensor, scenario)` for every valid input. Raises exactly what `base.translate` raises. Does not mutate its inputs. |
| `sensor_config` | `SensorConfig` | Loaded from `config/sensors/sensor_3.yaml` (`SENSOR_CONFIG_PATH`). |

`__all__ = ["GPS_UTC_OFFSET_S", "translate", "translate_with_clock_bug", "sensor_config"]`

## Observable behaviour at the gate (example scenario, unmodified)

| Submitted | Verdict | Failing checks | Check-4 reason |
|---|---|---|---|
| `translate_with_clock_bug` | BLOCKED | `[4]` | `timestamp_utc is 18.000 s ahead, limit is 0.5 s` |
| `translate` | ADMITTED | `[]` | `worst offset 0.000 s within 0.5 s (<n> Detections)` |

## Imports (import-linter)

`sensor3.py` imports `src.adapters.base` and `src.config.loader` only. Both
`no-ground-truth-leak` and `detection-schema-truth-free` remain kept.
