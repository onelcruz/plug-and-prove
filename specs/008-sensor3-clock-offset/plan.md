# Implementation Plan: Sensor 3 adapter with an injected clock-offset bug

**Branch**: `feature/8-sensor3-clock-offset` | **Date**: 2026-11-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/008-sensor3-clock-offset/spec.md`

## Summary

Add a third sensor on the unchanged #6 `SensorAdapter` contract: `config/sensors/sensor_3.yaml`
plus `src/adapters/sensor3.py`. The module exports two adapters:

- `translate_with_clock_bug`: the shared `base.translate` output, re-stamped with the sensor's
  GPS clock reading (UTC + `GPS_UTC_OFFSET_S` = 18.0 s), labelled as UTC.
- `translate`: the same reading with `GPS_UTC_OFFSET_S` subtracted, so its output is identical
  to `base.translate`.

The demo "toggle" is which callable is submitted to the #7 `ConformanceGate`; wiring that into
the run configuration is #13's job (noted on #13). Tests prove the fail → fix → pass beat on one
gate (BLOCKED by check 4 alone → ADMITTED on 7/7) with the example scenario untouched. No
harness, schema, simulator or `ScenarioConfig` change.

## Technical Context

**Language/Version**: Python 3.11 (CI); local dev also runs 3.10.

**Primary Dependencies**: pydantic v2 (existing `Detection`/`Heartbeat`/`SensorConfig`), numpy
via the simulator. No new dependencies.

**Storage**: One new YAML file under `config/sensors/`.

**Testing**: pytest; `ruff check .`; `lint-imports` (contracts `no-ground-truth-leak` and
`detection-schema-truth-free`).

**Target Platform**: Offline, single laptop (Principle II).

**Project Type**: Python library and demo pipeline (single project).

**Performance Goals**: The fail → fix → pass test plus the 3-sensor simulation stay within #7
SC-005's 60 s budget (SC-003).

**Constraints**: Must not edit `src/conformance/`, `src/adapters/base.py`,
`src/adapters/messages.py`, `src/simulator/`, `src/config/models.py`, or any `ScenarioConfig`
value (FR-009). The fix is adapter code, never a limit change (user instruction).

**Scale/Scope**: 1 YAML, 1 adapter module (~40 lines), 1 test module, 1 architecture pointer.

## Constitution Check

*GATE: must pass before Phase 0; re-checked after Phase 1 design.*

- **I. Architecture-first**: Implements §4 check 4's demo failure and the §10 sensor-3 sequence.
  §2's `config/sensors/` comment lists "offsets", which this design does not put in YAML
  (clarification Q1). That word is removed in the implementing PR, and the PR body says so
  (research.md R6). ✅ planned
- **II. Offline & simulated**: In-process only. ✅
- **III. Test-first & CI-gated**: The sneakiest-input fixtures (below) are written and seen to
  misbehave before `sensor3.py` exists. The fail → fix → pass sequence is one automated test.
  Timestamp arithmetic is numeric logic, so an independent review (`gh pr edit <N>
  --add-reviewer "@copilot"`) is requested before merge and its outcome recorded. ✅ planned
- **IV. Narrow, contract-bound**: New files only in `src/adapters/` (the issue's package) and
  `config/sensors/`, plus the architecture-doc edits. Sensor 3 plugs in through the
  `SensorAdapter` protocol, which demonstrates §3's "one adapter module + one config entry"
  claim. ✅
- **V. Reproducibility**: The adapter adds no randomness. Sensor 3 is appended after sensors 1
  and 2 when spawning RNG streams, so their streams are byte-identical (tested, SC-005). ✅
- **VI. Explainability**: The check-4 FAIL reason ("timestamp_utc is 18.000 s ahead, limit is
  0.5 s") is asserted verbatim. ✅
- **VII. Architecture health & gates**: Unsettled (rules 3 and 4). Spec, clarify, plan, tasks
  and analyze artifacts are permanent in this folder. `src.adapters` stays inside
  `no-ground-truth-leak`; `sensor3.py` imports only `src.adapters.base` and
  `src.config.loader`. ✅

**Post-design re-check**: no violations; Complexity Tracking not needed.

## Key design (details in research.md)

- **R1 GPS clock model**: The GPS clock is modelled inside the adapter (spec FR-008). The
  simulator's raw `t_s` stays truth-aligned; changing it would be invisible to check 4, which
  measures against `start_utc + raw.t_s`.
- **R2 Every message shifted**: The offset shifts `timestamp_utc` on every `Detection` and
  `Heartbeat`, and leaves `Heartbeat.t_s` and all other fields alone. Verified with the merged
  harness: +18 s fails check 4 alone on sensors 1 and 2 (reason "timestamp_utc is 18.000 s
  ahead, limit is 0.5 s").
- **R3 Sensor-3 values**: 1 Hz in a [0.5, 1.5] Hz band, `accuracy_m` 5, `range_m` 2500,
  `heartbeat_timeout_s` 2.0, `dropout_probability` 0.03, positioned at 38.8960, −77.0280 (about
  0.9 km NE of the defended-area centre). The drone is within range in 606 of 801 truth samples,
  and the prototype run produced 174 drone detections. With `base.translate` it passes 7/7.
- **R4 Exact fix**: At `start_utc` ≈ 1.7e9 the float64 ulp is 2⁻²² s, and 18 s is a whole
  number of ulps, so `(start_utc + t_s + 18) − 18` is exact. The fixed output equals
  `base.translate`'s exactly (FR-006). Probed on sensor 3's 1 Hz stream and sensor 2's 5 Hz
  stream.
- **R5 Guard test**: The FR-004 guard compares constants (`GPS_UTC_OFFSET_S >
  SCENARIO.max_clock_offset_s`), not harness outcomes. Probe found: at `start_utc` ≈ 1.7e9 an
  offset of 0.5000001 s still PASSES check 4 because it is below one timestamp ulp
  (~2.4e-7 s).

### Accepted limitation (offset is a constant)

The constant models one specific fault: GPS time labelled as UTC (GPS − UTC = 18 s since
2017-01-01). If a future leap second is announced, the constant goes stale. That doesn't matter
for a simulated demo, and the name and comment make the dependency obvious.

## Project Structure

### Documentation (this feature)

```text
specs/008-sensor3-clock-offset/
├── spec.md
├── plan.md              # this file
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── sensor3-adapter.md
├── checklists/
│   └── requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
config/sensors/
└── sensor_3.yaml            # NEW: sensor-3 config (R3); no offset field

src/adapters/
└── sensor3.py               # NEW: GPS_UTC_OFFSET_S, translate_with_clock_bug, translate, sensor_config

tests/
└── test_sensor3.py          # NEW: config, adapter, fail → fix → pass, guards, stream isolation

docs/architecture.md         # §2 comment drops "offsets"; one-line #8 pointer under §10
```

Not touched: `src/conformance/`, `src/adapters/base.py`, `src/adapters/messages.py`,
`src/simulator/`, `src/config/`, `config/scenarios/`, `.importlinter`,
`tests/conformance_fixtures.py` (its `SENSORS` tuple stays sensors 1 and 2, so the #7 tests are
unaffected).

**Structure Decision**: Single project. Sensor 3 mirrors `sensor2.py` and `sensor_2.yaml`.

### Test-quality requirements (copilot-instructions "While implementing")

- **Sneakiest-input failing fixtures** (written first; each must be shown to slip past a naive
  assertion before the real test is accepted):
  1. *Offset equal to the limit* (0.5 s): passes check 4 because the limit is inclusive. The
     FR-004 guard test must reject it. Fixture: guard predicate evaluated with 0.5 → False.
  2. *Offset on `Detection`s only*: also fails check 7. The "BLOCKED by check 4 **only**"
     assertion helper must reject it. Fixture: a Detections-only shifted adapter; the helper
     raises.
  3. *Fixed by loosening the limit*: submitting the buggy adapter with `max_clock_offset_s`
     raised to 20 s is ADMITTED. The "scenario unmodified" assertion must reject it. Fixture:
     a scenario copy with the raised limit; equality with the freshly loaded example scenario
     fails.
  4. *"Fix" that over-corrects* (subtracts twice, −18 s): still BLOCKED by check 4 ("behind").
     The fail → fix test must require ADMITTED, not merely "different reason".
- **Known-answer tests (external values)**:
  - `GPS_UTC_OFFSET_S == 18.0`: GPS − UTC is 18 s since 2017-01-01 (IERS Bulletin C 52; the
    U.S. Naval Observatory GPS time-transfer notes). Cited in the constant's comment.
  - The first buggy timestamp for `t_s` = 0 is 1,735,689,618.0, i.e. 2025-01-01T00:00:18Z (from
    an epoch converter, given `start_utc` 1,735,689,600 = 2025-01-01T00:00:00Z).
- **Round-trip test**: `translate(raw)` equals `base.translate(raw)` exactly for sensor 3's real
  stream, because subtracting `GPS_UTC_OFFSET_S` inverts the GPS clock reading.

## Architecture doc update (in the implementing PR)

- §2 `config/sensors/` comment: "(accuracy, rate, dropout, offsets)" → "(accuracy, rate,
  dropout)". Clock offsets live in adapter code (#8, clarification Q1).
- §10: one-line pointer under the sensor-3 sequence: "Implemented in #8: see
  `specs/008-sensor3-clock-offset/`."
- §13: no change. The `sensor_id` → adapter lookup bullet stays with #13.

## PR body requirements (recorded so they aren't lost)

- First line: `Classification: unsettled — rules 3 and 4 (toggle form, offset size and sensor-3
  config not pinned in §2–§11; materially different designs possible).`
- Paste the `/speckit-analyze` summary table.
- "Architecture doc" section: the §2 comment change and the §10 pointer.
- State that no `ScenarioConfig` value changed (`max_clock_offset_s` stays 0.5) and that the
  fix is adapter code.
- Note the #13 comment about wiring the toggle.
- The 0.5000001 s ulp observation (R5), and why the guard compares constants.
- Independent review outcome (`@copilot`), with every finding addressed or dismissed with
  reasoning.

## Complexity Tracking

Not applicable. No constitution violations.
