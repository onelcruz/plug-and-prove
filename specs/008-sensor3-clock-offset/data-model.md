# Data Model: Sensor 3 adapter with an injected clock-offset bug

No new types. Sensor 3 reuses the existing #6/#7 entities.

## Sensor-3 configuration (`SensorConfig`, existing type)

Source: `config/sensors/sensor_3.yaml`, loaded by `src.config.loader.load_sensor_config`.

| Field | Value | Validation (existing `SensorConfig` rules) |
|---|---|---|
| `sensor_id` | `sensor-3` | distinct from `sensor-1`, `sensor-2` and the `sensor-3-test` fixture |
| `accuracy_m` | 5.0 | > 0; ≤ `max_accuracy_m` |
| `range_m` | 2500 | > 0 |
| `update_rate_hz` | 1.0 | `min_hz` ≤ rate ≤ `max_hz` |
| `dropout_probability` | 0.03 | in [0, 1] |
| `heartbeat_timeout_s` | 2.0 | > 1 / `update_rate_hz` (1.0 s) |
| `min_hz` / `max_hz` | 0.5 / 1.5 | |
| `max_accuracy_m` | 50.0 | |
| `lat` / `lon` | 38.8960 / −77.0280 | within ±90 / ±180 |

There is no offset field (clarification Q1).

## Clock constant

| Name | Value | Meaning |
|---|---|---|
| `GPS_UTC_OFFSET_S` | 18.0 | GPS time − UTC since 2017-01-01 (leap seconds). Must be > the example scenario's `max_clock_offset_s` (0.5). |

## Message transformation (per message from `base.translate`)

| Callable | `timestamp_utc` | Every other field |
|---|---|---|
| `base.translate` (reference) | `start_utc + t_s` | reference |
| `translate_with_clock_bug` | `start_utc + t_s + GPS_UTC_OFFSET_S` | identical to the reference |
| `translate` | `start_utc + t_s` = reference (taken directly, no float round trip; research.md R4) | identical to the reference |

## Gate state transitions for `sensor-3` (existing `ConformanceGate`)

```text
(absent) --submit(translate_with_clock_bug)--> BLOCKED  [check 4 FAIL only; admitted_detections = []]
BLOCKED  --submit(translate)-----------------> ADMITTED [7/7 PASS; admitted_detections = real-stream Detections]
```

A re-submit replaces the verdict in place: `results()` keeps one sensor-3 entry, in its
first-submitted position.
