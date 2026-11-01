# Research: Sensor 3 adapter with an injected clock-offset bug

All `[NEEDS CLARIFICATION]` items were resolved in spec.md's 2026-11-01 clarification session.
This file records the design decisions that follow from them, and the probes run against the
merged #7 harness (`main` at `f6ede37`).

## R1: Where the GPS clock lives

- **Decision**: Inside `src/adapters/sensor3.py`. A private helper re-stamps `base.translate`'s
  output with the sensor's clock reading, `timestamp_utc + GPS_UTC_OFFSET_S`.
  - `translate_with_clock_bug` returns that reading labelled as UTC.
  - `translate` reports UTC directly, i.e. `base.translate`'s output (amended after the PR #30
    review; see R4).
- **Rationale**: Check 4 measures each `Detection` against `start_utc + raw.t_s`. If the
  simulator produced GPS-shifted raw `t_s`, the harness's reference would shift too, so the bug
  would be invisible. Shifting raw `t_s` would also change the simulator (FR-009). The
  fixed adapter must remove the 18 s, and the bug (the GPS reading labelled as UTC) is only
  meaningful if it is modelled in the adapter.
- **Alternatives considered**: An offset field in `SensorConfig`/YAML (rejected in clarification
  Q1). A GPS-time raw stream from the simulator (invisible to check 4, and forbidden by FR-009).
  A fixed `translate` that is literally `base.translate` (re-exported, as in `sensor1.py`):
  functionally the same, but a separate function keeps the buggy/fixed pair readable and
  documents the fix.

## R2: Which fields the bug touches

- **Decision**: Only `timestamp_utc`, on every `Detection` and every `Heartbeat`.
  `Heartbeat.t_s`, `detection_id`, `raw_payload` and all positional fields are unchanged.
- **Rationale**: #7 recorded that a Detections-only offset fails check 7 too. Probe on `main`,
  applying +18 s to every message's `timestamp_utc`:
  - sensor-1: BLOCKED, failing checks `[4]`, reason "timestamp_utc is 18.000 s ahead, limit is
    0.5 s".
  - sensor-2: same result.
  - −18 s: failing checks `[4]`, reason "... 18.000 s behind ...".
- **Alternatives considered**: Also shifting `Heartbeat.t_s`. Rejected: `t_s` is simulator
  time, not the sensor's clock, and check 7 uses it to match withheld ticks.

## R3: Sensor-3 configuration values

- **Decision**: `config/sensors/sensor_3.yaml` with these values:

  | Field | Value |
  |---|---|
  | `sensor_id` | `sensor-3` |
  | `accuracy_m` | 5.0 |
  | `range_m` | 2500 |
  | `update_rate_hz` | 1.0 |
  | `dropout_probability` | 0.03 |
  | `heartbeat_timeout_s` | 2.0 |
  | `lat`, `lon` | 38.8960, −77.0280 |
  | `min_hz`, `max_hz` | 0.5, 1.5 |
  | `max_accuracy_m` | 50.0 |

- **Rationale**:
  - A distinct, realistic short-range, precise, slow sensor (EO/IR-like), unlike sensor 1
    (2 Hz, 15 m, 5 km) and sensor 2 (5 Hz, 8 m, 3.5 km).
  - It passes every `SensorConfig` validator: 2.0 > 1/1.0, 0.5 ≤ 1.0 ≤ 1.5, and 5 ≤ 50.
  - Placed about 0.9 km NE of the defended-area centre, on the drone's inbound bearing (45°).
    Prototype run: the drone is within 2500 m in 606 of 801 truth samples, and the run produced
    174 drone-matching detections. Sensor 3 therefore adds to §10's "3 sensors" picture.
  - With `base.translate`, the prototype passed 7/7 checks (709 probe+real Detections, measured
    rate 1.000 Hz, 177 Detections and 4 Heartbeats on the gap probe).
- **Alternatives considered**: Co-locating with the centre (default `lat`/`lon`). Rejected: the
  drone path is less covered, and sensor 3 would add little to the picture.
- **Name clash check**: `tests/test_adapter_extensibility.py` uses `sensor-3-test`, which is
  distinct.

## R4: Exactness of the fix

- **Decision**: The fixed `translate` must equal `base.translate` exactly (`==` on the message
  lists), not merely within tolerance.
- **Rationale**: The first design recovered UTC as `(utc + 18.0) − 18.0`. A probe showed this
  exact for every message of sensor 3's real stream (1 Hz) and of sensor 2's (5 Hz) at
  `start_utc` ≈ 1.7e9, but the Copilot review of PR #30 showed it is **not** exact where adding
  18 s crosses a float64 binade (e.g. `start_utc` = 1073741823.9999999, just below 2³⁰, gives
  1073741824.0). Resolved: the fixed `translate` returns `base.translate`'s output directly, so
  exactness holds for every epoch. A regression test covers the boundary epochs.
- **Alternatives considered**: A tolerance-based equality. Rejected because it would hide a
  wrong subtraction smaller than the tolerance.

## R5: Guard test compares constants

- **Decision**: The FR-004 guard asserts `GPS_UTC_OFFSET_S > SCENARIO.max_clock_offset_s`, using
  the freshly loaded example scenario. Separately, the fail → fix test asserts that the scenario
  submitted equals a fresh load of `example_scenario.yaml`.
- **Rationale**: Probe: an offset of 0.5000001 s PASSES check 4 because it is under one
  timestamp ulp at `start_utc` ≈ 1.7e9. A harness-based guard would wrongly tell "barely above
  the limit" apart from "at the limit". The constant comparison is exact and states the intent.

## R6: Architecture doc changes

- **Decision**:
  - In §2's `config/sensors/` comment, drop "offsets".
  - Add one §10 pointer line: "Implemented in #8: see `specs/008-sensor3-clock-offset/`."
- **Rationale**: copilot-instructions say to "update `docs/architecture.md` in the same PR" on a
  design deviation. The §2 comment implied YAML offsets, which clarification Q1 rejected. §3
  (lines 74–76) already places the clock-offset bug "in the adapter layer in #6/#8", so it is
  consistent and unchanged.
- **Alternatives considered**: Leaving §2 as is. Rejected: the doc would contradict the code.

## R7: How the toggle is wired

- **Decision**: Not in #8. Posted on #13
  (https://github.com/onelcruz/plug-and-prove/issues/13#issuecomment-6560138928) that the toggle
  is the choice of callable submitted to the gate.
- **Rationale**: §13's open bullet assigns the `sensor_id` → adapter lookup to #13
  orchestration.
