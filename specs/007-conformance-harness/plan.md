# Implementation Plan: Conformance harness (7 contract checks + pass/fail report)

**Branch**: `feature/7-conformance-harness` | **Date**: 2026-10-31 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/007-conformance-harness/spec.md`

## Summary

Build `src/conformance/` as a pre-ingest **gate** (§12 row 3): seven pure check functions, a
harness that runs an adapter on three inputs (the caller's real raw stream, a deterministic
full-schedule probe stream, and a probe stream with a contiguous gap), a `ConformanceGate` that is
the only path from an adapter's `Detection`s to downstream consumers, and a deterministic Markdown
report. Thresholds are added to config as required fields: sensor-declared limits (`min_hz`,
`max_hz`, `max_accuracy_m`) on `SensorConfig`, and system acceptance limits (`max_clock_offset_s`,
`min_alt_m`, `max_alt_m`) on `ScenarioConfig`. A type-only import fix in
`src/simulator/detections.py` lets the harness use `RawDetection`/`expected_ticks`/`SensorAdapter`
without breaking `no-ground-truth-leak`, and `src.adapters` is re-added to that contract. This
resolves the four §13 bullets assigned to #7. Full decision record: [research.md](./research.md).

## Technical Context

**Language/Version**: Python 3.11+ (CI runs 3.11)

**Primary Dependencies**: `pydantic` (existing). No new dependencies.

**Storage**: N/A. In-process objects; the report is returned as a string (persisting to `runs/` is
#13).

**Testing**: `pytest`; style matches `tests/test_adapters.py`.

**Target Platform**: Single local machine, offline (Principle II).

**Project Type**: Single Python project (existing `src/` layout).

**Performance Goals**: Full harness against both known-good adapters < 60 s (epic / §4). Expected
well under 1 s: ~1,260 probe ticks total plus the real streams, all pydantic validation.

**Constraints**: No ground-truth imports (enforced by `lint-imports`); no RNG in the harness
(probes are deterministic); checks 5–7 invariant to a constant clock offset.

**Scale/Scope**: 7 checks, 2 known-good adapters plus local broken-adapter test fixtures. Sensor 3
itself is #8.

## Constitution Check

*GATE: must pass before Phase 0; re-checked after Phase 1 design.*

- **I. Architecture-first**: Implements §4. Deviates from §4's wording for checks 3 and 7 and
  resolves four §13 bullets, so architecture.md is updated in this PR (research.md R11). ✅ planned
- **II. Offline & simulated**: In-process only; no network. ✅
- **III. Test-first & CI-gated**: Every check has pass and fail fixtures. The geometry (check 3) and
  numeric logic (checks 4–6) are non-trivial, so an independent review is required before merge
  (`gh pr edit <N> --add-reviewer "@copilot"`), and its outcome goes in the PR body. ✅ planned
- **IV. Narrow, contract-bound**: Work stays in `src/conformance/` plus `src/config/models.py`
  (extend only). **One disclosed exception:** `src/simulator/detections.py` gets a type-only
  `TYPE_CHECKING` guard (no behavior change). The harness touches adapters only through the
  `SensorAdapter` protocol. ✅ with disclosed exception
- **V. Reproducibility**: The harness introduces no randomness, and probes are deterministic.
  Report determinism is tested (byte-identical). Ruff's `TID251` ban continues to apply. ✅
- **VI. Explainability**: Every `CheckResult` carries a validated, non-empty, single-line reason. ✅
- **VII. Architecture health & gates**: Unsettled (rules 1 and 3). The spec, clarify, plan, tasks,
  and analyze artifacts are permanent in this folder. Module boundaries stay mechanically enforced:
  `src.adapters` is re-added to `no-ground-truth-leak`, offsetting `exclude_type_checking_imports`. ✅

**Post-design re-check**: no violations; Complexity Tracking not needed.

## Key design (details in research.md)

| Item | Decision | Ref |
|---|---|---|
| Check 7 | Adapter-side, count-based response to harness-withheld ticks; fusion coasting moves to #9 | R1, spec Q1 |
| Check 4 reference | `start_utc + raw.t_s` of inputs the harness itself supplied, compared sorted | R2, spec Q2 |
| Inputs | Real stream (checks 1–4) plus full and gap probe streams (checks 1–7) | R3, spec Q3 |
| Check 3 bound | `range_m + 6 × accuracy_m` from sensor position | R4, spec Q4 |
| Limits | Sensor: `min_hz`, `max_hz`, `max_accuracy_m`. Scenario: `max_clock_offset_s`, `min_alt_m`, `max_alt_m` | R5, spec Q5 |
| Import boundary | `TYPE_CHECKING` guard plus `exclude_type_checking_imports`; re-add `src.adapters` | R6 |
| Offset invariance | Checks 5–7 use counts, intervals, and spans only | R7, FR-009a |
| Schema check | Re-validate instances (catches `model_construct`/`model_copy` bypass); non-models FAIL | R8 |
| Isolation | Adapter and check exceptions → FAIL for the dependent checks only | R9 |

### Accepted limitation (clock-offset reference)

Check 4's reference works only because the harness supplies the adapter's inputs in-process. A real
networked sensor, whose raw feed the harness does not generate, would need a different reference
(for example a trusted time source or a known-time calibration target). Out of scope for this
demo (§3.3, §12 row 2). Recorded per the user's instruction during `/speckit-clarify` (Q2).

### Accepted risk (sensor-declared limits)

`min_hz`, `max_hz`, and `max_accuracy_m` are sensor-declared by design: they describe the sensor's
own spec, and checks 2 and 5 verify that the adapter honors it. The limits a faulty sensor could
otherwise loosen for itself (clock offset, altitude plausibility) live on `ScenarioConfig`.

## Project Structure

### Documentation (this feature)

```text
specs/007-conformance-harness/
├── spec.md               # /speckit-specify + /speckit-clarify
├── checklists/requirements.md
├── research.md           # decisions R1–R11
├── data-model.md
├── contracts/harness-api.md
├── quickstart.md
├── plan.md               # this file
└── tasks.md              # /speckit-tasks
```

### Source Code (repository root)

```text
src/
├── conformance/
│   ├── __init__.py         # existing (empty)
│   ├── results.py          # NEW: CheckResult, HarnessResult
│   ├── probes.py           # NEW: probe_position, withheld_tick_indices, build_probe_stream
│   ├── checks.py           # NEW: the 7 check functions
│   ├── harness.py          # NEW: run_harness -> HarnessRun
│   ├── gate.py             # NEW: ConformanceGate
│   └── report.py           # NEW: render_markdown
├── config/models.py        # EXTEND: 3 SensorConfig + 3 ScenarioConfig fields and validators
└── simulator/detections.py # PRINCIPLE IV EXCEPTION: TruthObject import under TYPE_CHECKING

config/
├── sensors/example_sensor.yaml   # UPDATE: min_hz, max_hz, max_accuracy_m
├── sensors/sensor_2.yaml         # UPDATE: min_hz, max_hz, max_accuracy_m
└── scenarios/example_scenario.yaml  # UPDATE: max_clock_offset_s, min_alt_m, max_alt_m

.importlinter               # UPDATE: exclude_type_checking_imports; re-add src.adapters
docs/architecture.md        # UPDATE: §4 pointer + checks 3/7 wording; §13 four bullets resolved

tests/
├── test_config_loader.py         # UPDATE: new-field validators
├── test_detections.py            # UPDATE: fixtures pass new required fields
├── test_adapters.py              # UPDATE: fixtures pass new required fields
├── test_adapter_extensibility.py # UPDATE: fixtures pass new required fields
├── test_conformance_checks.py    # NEW: pass + fail fixture per check, known-answer tests
├── test_conformance_harness.py   # NEW: end-to-end sensors 1 & 2; clock-offset isolation; < 60 s
├── test_conformance_gate.py      # NEW: gate blocks / re-admits; stub-fusion consumer
└── test_conformance_report.py    # NEW: 7 rows, one-line reasons, deterministic
```

**Structure Decision**: Populate the existing `src/conformance/` placeholder package (§2), with
one module per responsibility so each check is independently importable and testable.

### Test-quality requirements (copilot-instructions "While implementing")

- **Known-answer tests (external values)**:
  - Check 3: a detection exactly 1° of latitude north of the sensor lies 111,195 m away (the
    textbook figure for a 6,371 km spherical Earth: π/180 × 6,371,000). With `range_m` = 100,000
    and `accuracy_m` = 1 it FAILS; with `range_m` = 111,200 it PASSES.
  - Check 5: 11 detections spaced exactly 0.5 s apart measure 2.0 Hz (hand-derived: 10 intervals
    over 5 s).
  - Check 4: inputs with `t_s` [0, 0.5, 1.0], `start_utc` 1,735,689,600 (2025-01-01T00:00:00Z, from
    an epoch converter), and outputs shifted by +2.0 s FAIL with "2.000 s ahead".
- **Round-trip test**: `probe_position` places the probe `range_m / 2` east using
  `offset_to_latlon`; `distance_m` back to the sensor recovers `range_m / 2` within 1e-6 relative.

## Architecture doc update (in the implementing PR)

Per research.md R11:

- §4: one-line pointer "Resolved in #7: see `specs/007-conformance-harness/`".
- §4 check 3 reworded to the sensor coverage circle (`range_m + 6 × accuracy_m` from the sensor).
- §4 check 7 reworded to the adapter-side gap response; fusion coasting is verified in #9.
- §13: strike the four bullets assigned to #7 (`[min_hz, max_hz]`, real liveness, check-5 cadence,
  `raw_payload.t_s`) and add one "Resolved in #7" pointer line. The orchestration-mapping bullet
  (#13) stays.

## PR body requirements (recorded so they aren't lost)

- First line: `Classification: unsettled — rules 1 and 3 (§13 questions assigned to #7; thresholds
  not pinned in §2–§11).`
- Paste the `/speckit-analyze` summary table.
- "Architecture doc" section: note the §4 check 3 and check 7 changes (user instruction).
- Principle IV exception: the `detections.py` `TYPE_CHECKING` change.
- Import probes: conformance → `simulator.detections` ALLOWED; conformance →
  `simulator.trajectories` BLOCKED; adapters → `simulator.trajectories` BLOCKED.
- Independent review outcome (`@copilot`), with every finding addressed or dismissed with reasoning.

## Complexity Tracking

Not applicable. No unjustified constitution violations; the Principle IV exception is disclosed
above.
