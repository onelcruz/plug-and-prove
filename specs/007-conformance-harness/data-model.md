# Data model: Conformance harness (#7)

## Config additions (`src/config/models.py`, extend — do not redefine)

### `SensorConfig` (+3 required fields)

| Field | Type | Meaning |
|---|---|---|
| `min_hz` | `PositiveFloat` | Lowest acceptable measured `Detection` rate (check 5) |
| `max_hz` | `PositiveFloat` | Highest acceptable measured `Detection` rate (check 5) |
| `max_accuracy_m` | `PositiveFloat` | Upper plausibility bound for `Detection.accuracy_m` (check 2) |

Validators (model-level, alongside #6's `heartbeat_timeout_s` validator):
`min_hz <= update_rate_hz <= max_hz`; `accuracy_m <= max_accuracy_m`.

### `ScenarioConfig` (+3 required fields)

| Field | Type | Meaning |
|---|---|---|
| `max_clock_offset_s` | `PositiveFloat` | Max \|`timestamp_utc` − reference\| (check 4) |
| `min_alt_m` | `NonNegativeFloat` | Lower plausibility bound for `Detection.alt_m`, meters AGL (check 2) |
| `max_alt_m` | `PositiveFloat` | Upper plausibility bound for `Detection.alt_m` (check 2) |

Validators: `min_alt_m < max_alt_m`; every `drones[*].altitude_m`, `birds[*].altitude_m`, and
`clutter.altitude_m` lies within `[min_alt_m, max_alt_m]`.

## Harness entities (`src/conformance/results.py`, pydantic, frozen)

### `CheckResult`

| Field | Type | Rule |
|---|---|---|
| `number` | `int` | 1–7 |
| `name` | `str` | One of the 7 canonical names (below) |
| `passed` | `bool` | |
| `reason` | `str` | Non-empty, single line (validator rejects `\n`) |

Canonical names: 1 `schema`, 2 `units`, 3 `coordinate_frame`, 4 `clock_offset`, 5 `update_rate`,
6 `heartbeat`, 7 `dropped_messages`.

### `HarnessResult`

| Field | Type | Rule |
|---|---|---|
| `sensor_id` | `str` | From the `SensorConfig` under test |
| `checks` | `tuple[CheckResult, ...]` | Exactly 7, numbers 1–7 in order (validator) |
| `admitted` | `bool` (computed property) | `all(c.passed for c in checks)` |

### `HarnessRun` (`src/conformance/harness.py`, return type of `run_harness`)

| Field | Type | Rule |
|---|---|---|
| `result` | `HarnessResult` | The 7 check outcomes for this adapter |
| `real_detections` | `list[Detection]` | `Detection`s from the real-stream run only (never probe output, never `Heartbeat`s); what the gate stores and may release |

## Gate state (`src/conformance/gate.py`)

`ConformanceGate` holds, per `sensor_id`: the latest `HarnessResult` and the real-stream
`Detection`s from that same run.

State transitions per sensor:

```text
(unknown) --submit, all pass--> ADMITTED --submit, any fail--> BLOCKED
(unknown) --submit, any fail--> BLOCKED  --submit, all pass--> ADMITTED
```

A re-submit replaces the previous result and stored detections (§10 "fix → re-run → PASS").
`admitted_detections(sensor_id)` returns the stored `Detection`s only in ADMITTED; otherwise `[]`.
`Heartbeat`s are never stored or released.

## Probe inputs (`src/conformance/probes.py`, no persistent state)

`RawDetection` lists (existing model from `src/simulator/detections.py`):

- **full probe**: one per tick of `expected_ticks(update_rate_hz, duration_s)` at the fixed probe
  position.
- **gap probe**: the full probe minus the withheld tick indices (research.md R3).
