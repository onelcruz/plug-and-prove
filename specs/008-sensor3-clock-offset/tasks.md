# Tasks: Sensor 3 adapter with an injected clock-offset bug

**Input**: Design documents from `specs/008-sensor3-clock-offset/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/sensor3-adapter.md,
quickstart.md

**Tests**: Required. The spec mandates automated proof (FR-004, FR-007, SC-001–SC-005), and
copilot-instructions require sneakiest-input failing fixtures before implementation.

**Organization**: Tasks are grouped by user story. All three stories are P1 and are delivered in
order US1 → US2 → US3, because US3 composes US1 and US2.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1, US2 or US3 (spec.md)

Shared test module: `tests/test_sensor3.py`. It imports `SCENARIO`, `SENSORS` and the
`translate` reference from `tests/conformance_fixtures.py`, and builds sensor 3's real stream
with a module-level `@cache`d `run_simulation(SCENARIO, [*SENSORS, sensor3.sensor_config])`
(sensor 3 appended last, FR-010). `tests/conformance_fixtures.py` is **not** modified.

---

## Phase 1: Setup

- [ ] T001 Confirm the branch `feature/8-sensor3-clock-offset` contains `origin/main` (merge if
  behind) and that #6 and #7 are CLOSED. Run `ruff check . && lint-imports && python -m pytest`
  and record the baseline (expect `All checks passed!`, `2 kept, 0 broken`, 146 passed).

---

## Phase 2: Foundational (config + sneakiest-input fixtures)

**Purpose**: Sensor 3's config, and the assertion helpers every story's tests rely on, each
proven against its sneakiest broken input **before** `src/adapters/sensor3.py` exists.

- [ ] T002 [P] Create `config/sensors/sensor_3.yaml` with the research.md R3 values
  (`sensor-3`, 5.0 m, 2500 m, 1.0 Hz, dropout 0.03, heartbeat timeout 2.0, 38.8960/−77.0280,
  band 0.5–1.5 Hz, `max_accuracy_m` 50.0) and a header comment in the style of `sensor_2.yaml`
  stating it is distinct from sensors 1 and 2 and carries **no** clock-offset field
  (clarification Q1).
- [ ] T003 Create `tests/test_sensor3.py` with a config test: `load_sensor_config` on
  `sensor_3.yaml` returns the R3 values; `sensor_id` differs from `sensor-1`, `sensor-2` and
  `sensor-3-test`; the loaded model has no field whose name contains `offset` (FR-002, FR-005).
- [ ] T004 In `tests/test_sensor3.py`, add three assertion helpers and their red-fixture tests
  (plan.md "Sneakiest-input failing fixtures" 1–3). Each red-fixture test is written first and
  must FAIL against a naive stub of its helper (e.g. `return True`, "any check failed", or
  "verdict changed") before the real helper is written. Record each observed failure in the PR
  body.
  - `offset_exceeds_limit(offset_s, limit_s) -> bool` (strict `>`). Red fixture: `(0.5, 0.5)`
    → False; `(0.5000001, 0.5)` → True; `(18.0, 0.5)` → True.
  - `assert_blocked_by_check4_only(result)`: verdict not admitted, exactly `[4]` failing.
    Red fixture: a local `detections_only_offset_adapter` (+18 s on `Detection`s only, applied
    to sensor 1's real stream via `run_harness`), for which the helper must raise because
    check 7 also fails.
  - `assert_scenario_unmodified(scenario)`: equals a fresh `load_scenario_config` of
    `config/scenarios/example_scenario.yaml` (`model_dump()` equality). Red fixture:
    `SCENARIO.model_copy(update={"max_clock_offset_s": 20.0})`, for which the helper must
    raise.

**Checkpoint**: Config loads, and all helpers are proven to reject their sneakiest inputs.

---

## Phase 3: User Story 1 — Sensor 3 with the bug is blocked by check 4 alone (P1) 🎯 MVP

**Goal**: `translate_with_clock_bug` is BLOCKED by check 4 only, with an explanatory reason.

**Independent Test**: Submitting `translate_with_clock_bug` to a fresh gate with the unmodified
example scenario and sensor 3's real stream gives BLOCKED, failing `[4]`, reason
`timestamp_utc is 18.000 s ahead, limit is 0.5 s`, and `admitted_detections("sensor-3") == []`.

### Tests for User Story 1 (write first; confirm they fail with ImportError)

- [ ] T005 [US1] In `tests/test_sensor3.py`, add these tests:
  - **Guard**: `offset_exceeds_limit(GPS_UTC_OFFSET_S, fresh example scenario
    max_clock_offset_s)` is True (FR-004).
  - **Known answer**: `GPS_UTC_OFFSET_S == 18.0`, with a docstring citing GPS − UTC = 18 s since
    2017-01-01 (IERS Bulletin C 52) (FR-008).
  - **Known answer**: for a single `RawDetection` at `t_s` 0.0, the buggy `timestamp_utc` is
    1,735,689,618.0 (2025-01-01T00:00:18Z, external epoch converter).
- [ ] T006 [US1] In `tests/test_sensor3.py`, add a test comparing `translate_with_clock_bug`
  with `base.translate` on sensor 3's real stream. Same length, same message types in the same
  order, every `timestamp_utc` exactly `+ GPS_UTC_OFFSET_S`, and every other field equal,
  including `Heartbeat.t_s` and `detection_id` (FR-003, research.md R2). Also assert that the
  input list and its `RawDetection`s are unchanged after the call (deep-copy comparison;
  contract "does not mutate").
- [ ] T007 [US1] In `tests/test_sensor3.py`, add a gate test with a fresh `ConformanceGate`:
  - Submit `translate_with_clock_bug`, `sensor3.sensor_config`, `SCENARIO` and the real stream.
  - `assert_blocked_by_check4_only`.
  - The check-4 reason equals `timestamp_utc is 18.000 s ahead, limit is 0.5 s`.
  - `admitted_detections("sensor-3") == []`.
  - `render_markdown(gate.results())` contains sensor 3's BLOCKED section and that reason
    (US1 scenarios 1–3, SC-001).
  - `assert_scenario_unmodified(SCENARIO)`.

### Implementation for User Story 1

- [ ] T008 [US1] Create `src/adapters/sensor3.py`, mirroring `sensor2.py`'s docstring and layout:
  - `SENSOR_CONFIG_PATH` and `sensor_config` from `config/sensors/sensor_3.yaml`.
  - `GPS_UTC_OFFSET_S = 18.0`, with a comment: the sensor reports GPS time; GPS − UTC = 18 s
    (leap seconds since 1980-01-06; current since 2017-01-01, IERS Bulletin C 52).
  - Private `_gps_clock(raw, sensor, scenario)`: `base.translate` output with each
    `timestamp_utc + GPS_UTC_OFFSET_S` via `model_copy`.
  - `translate_with_clock_bug`: returns `_gps_clock(...)`, with a docstring saying it labels
    GPS time as UTC (the demo bug).
  - Imports only `src.adapters.base` and `src.config.loader`.
  - `__all__` per contracts/sensor3-adapter.md.
  - Run T005–T007 green.

**Checkpoint**: The demo failure is reproducible on its own.

---

## Phase 4: User Story 2 — Removing the bug passes all 7 checks (P1)

**Goal**: `translate` subtracts `GPS_UTC_OFFSET_S` and is ADMITTED 7/7 under the unmodified
scenario.

**Independent Test**: Submitting `translate` to a fresh gate gives ADMITTED, 7/7 PASS, and
`admitted_detections("sensor-3")` has one `Detection` per raw input, each with
`timestamp_utc == start_utc + t_s`.

### Tests for User Story 2 (write first; confirm they fail)

- [ ] T009 [US2] In `tests/test_sensor3.py`, add a round-trip test: `sensor3.translate(raw,
  ...) == base.translate(raw, ...)` exactly (list `==`) on sensor 3's real stream (FR-006,
  research.md R4). Also assert that `sensor3.translate is not base.translate`, so the
  "subtract" path is actually exercised (clarification Q2).
- [ ] T010 [US2] In `tests/test_sensor3.py`, add a gate test with a fresh gate:
  - Submit `translate`: the result is admitted, with all 7 checks passing.
  - `admitted_detections("sensor-3")` has length `len(raw)`, and its sorted `timestamp_utc`
    values equal the sorted `SCENARIO.start_utc + r.t_s` (US2 scenarios 1–2, SC-002).
  - `assert_scenario_unmodified(SCENARIO)` (SC-004).

### Implementation for User Story 2

- [ ] T011 [US2] In `src/adapters/sensor3.py`, add `translate(raw, sensor, scenario)`:
  `_gps_clock(...)` with each `timestamp_utc − GPS_UTC_OFFSET_S`. Its docstring says it
  converts the sensor's GPS clock reading to UTC (the fix). Run T009–T010 green.

**Checkpoint**: Both halves of the beat work separately.

---

## Phase 5: User Story 3 — Fail → fix → pass on one gate (P1)

**Goal**: One automated test proves the whole demo beat.

**Independent Test**: The test itself (below).

- [ ] T012 [US3] In `tests/test_sensor3.py`, add `test_fail_fix_pass_on_one_gate` (FR-007,
  SC-003):
  - Submit `sensor1.translate` and `sensor2.translate` with their configs and real streams
    from the same 3-sensor run.
  - Submit `sensor3.translate_with_clock_bug`; `assert_blocked_by_check4_only`.
  - Re-submit `sensor3.translate`; it is admitted.
  - `[r.sensor_id for r in gate.results()] == ["sensor-1", "sensor-2", "sensor-3"]`. Exactly one
    sensor-3 entry, now admitted (verdict flipped in place).
  - Sensors 1 and 2's results equal their results before sensor 3's submissions (US3
    scenario 2).
  - `assert_scenario_unmodified(SCENARIO)`.
- [ ] T013 [US3] In `tests/test_sensor3.py`, add the over-correction red fixture (plan.md fixture
  4): a local `double_subtract_adapter` (sensor 3's `translate` output minus another
  `GPS_UTC_OFFSET_S`). Submitting it after the buggy adapter stays BLOCKED, with a check-4
  reason containing `18.000 s behind`. This proves the fail → fix test's "admitted" assertion
  is what distinguishes a real fix.
- [ ] T014 [US3] In `tests/test_sensor3.py`, add the stream-isolation test (FR-010,
  SC-005): `run_simulation(SCENARIO, [*SENSORS, sensor3.sensor_config])` gives sensor-1 and
  sensor-2 raw streams equal to `real_streams()` (the 2-sensor run).

**Checkpoint**: The full demo beat is CI-guaranteed.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T015 [P] Update `docs/architecture.md` (research.md R6):
  - In §2, change the `config/sensors/` comment from "(accuracy, rate, dropout, offsets)" to
    "(accuracy, rate, dropout)".
  - Add one §10 line directly under the sensor-3 sequence diagram: "Implemented in #8: see
    `specs/008-sensor3-clock-offset/`."
  - No §12 or §13 change.
- [ ] T016 Run `git diff --stat origin/main` and confirm that only these paths changed:
  `config/sensors/sensor_3.yaml`, `src/adapters/sensor3.py`, `tests/test_sensor3.py`,
  `docs/architecture.md`, `specs/008-sensor3-clock-offset/**` and `.specify/feature.json` (if
  tracked). Nothing under `src/conformance/`, `src/simulator/`, `src/config/`,
  `config/scenarios/`, `src/adapters/base.py`, `src/adapters/messages.py` or
  `tests/conformance_fixtures.py` (FR-009).
- [ ] T017 Run `ruff check . && lint-imports && time python -m pytest`. Expect `All checks
  passed!`, `Contracts: 2 kept, 0 broken.`, all pass, and a wall time ≤ 60 s (SC-003). Paste
  the outputs in the PR body.
- [ ] T018 Walk through quickstart.md step 4 in a Python shell and confirm the BLOCKED and
  ADMITTED verdicts and reasons match contracts/sensor3-adapter.md.
- [ ] T019 Open the PR to `main` using `.github/pull_request_template.md` and plan.md's "PR body
  requirements" (first line is the classification; analyze table; architecture-doc section;
  "no ScenarioConfig value changed"; #13 note; R5 ulp note; red-fixture observations from
  T004). Then request the independent review with `gh pr edit <N> --add-reviewer "@copilot"`.
  Address or dismiss every finding with reasoning, and record the outcome in the PR body.

---

## Dependencies & Execution Order

- **Setup (T001)** → **Foundational (T002–T004)** → **US1 (T005–T008)** → **US2 (T009–T011)**
  → **US3 (T012–T014)** → **Polish (T015–T019)**.
- T003 needs T002. T004 does not need sensor 3 at all. T003 and T004 share
  `tests/test_sensor3.py`, so they run sequentially.
- US2 depends on US1's `_gps_clock` (T008). US3 depends on US1 and US2.
- T014 needs only `sensor3.sensor_config` (T002/T008), but shares `tests/test_sensor3.py`, so it is
  sequential.
- T015 is [P]: it touches docs only, and can be done at any point after T001.

## Parallel Example

```text
After T001:  T002 (config/sensors/sensor_3.yaml)  ||  T015 (docs/architecture.md)
```

## Implementation Strategy

1. MVP = Phases 1–3: the demo failure (US1) exists and is explained.
2. Add US2: the fix passes on its own.
3. Add US3: the full beat is one test, and sensors 1 and 2 are proven unaffected.
4. Polish: architecture doc, scope check, full gate, PR and independent review.
