# Tasks: Conformance harness (7 contract checks + pass/fail report)

**Input**: Design documents from `specs/007-conformance-harness/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/harness-api.md, quickstart.md

**Tests**: Required. Issue #7's acceptance criteria demand a passing and a failing fixture per
check, an end-to-end run, and a gate test.

**Organization**: US1–US3 are all P1. They are ordered by dependency: US3 (the checks) → US1
(harness + gate admits) → US2 (gate blocks + re-admits). US4 (P2, the report) comes last.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US4 from spec.md

---

## Phase 1: Setup (prerequisite #26 — research.md R6)

**Purpose**: Confirm the import-boundary fix, split out of #7 into #26 (PR #27) to satisfy
Principle IV, is on `main` before any #7 code is written. #7 makes **no** edits to
`src/simulator/` or `.importlinter`.

- [ ] T001 Confirm #26 (PR #27) is merged, then merge `origin/main` into
      `feature/7-conformance-harness`. If it isn't merged, stop (`.github/copilot-instructions.md`
      "Before writing code", step 1).
- [ ] T002 Read-only check that `.importlinter` on the merged branch has
      `exclude_type_checking_imports = True` and `src.adapters` in `no-ground-truth-leak`, and that
      `src/simulator/detections.py` imports `TruthObject` only under `TYPE_CHECKING`. If anything
      differs, stop and report (depends on T001).
- [ ] T003 Run `lint-imports` (expect `Contracts: 2 kept, 0 broken.`), then the three probes from
      quickstart.md §2 (conformance → `simulator.detections` ALLOWED; conformance →
      `simulator.trajectories` BLOCKED; adapters → `simulator.trajectories` BLOCKED). Record the
      output for the PR body, delete the probe files, and confirm `git status` shows none (depends
      on T002).

---

## Phase 2: Foundational (config limits, result types, probes)

**Purpose**: Shared prerequisites for every check and story.

**⚠️ CRITICAL**: No user-story work can begin until this phase is complete.

- [ ] T004 In `src/config/models.py`, add required `min_hz: PositiveFloat`, `max_hz: PositiveFloat`,
      and `max_accuracy_m: PositiveFloat` to `SensorConfig`. Extend its model validator to reject
      `min_hz > update_rate_hz`, `update_rate_hz > max_hz`, and `accuracy_m > max_accuracy_m`, with
      messages naming both values (FR-015, data-model.md).
- [ ] T005 In `src/config/models.py`, add required `max_clock_offset_s: PositiveFloat`,
      `min_alt_m: NonNegativeFloat`, and `max_alt_m: PositiveFloat` to `ScenarioConfig`, plus a model
      validator rejecting `min_alt_m >= max_alt_m` and any `drones[*].altitude_m`,
      `birds[*].altitude_m`, or `clutter.altitude_m` outside `[min_alt_m, max_alt_m]`. Update the
      module docstring's list of #7 additions (FR-015; depends on T004, same file).
- [ ] T006 [P] Add `min_hz: 1.5`, `max_hz: 2.5`, `max_accuracy_m: 50.0` to
      `config/sensors/example_sensor.yaml` (values and rationale: research.md R5; depends on T004).
- [ ] T007 [P] Add `min_hz: 4.0`, `max_hz: 6.0`, `max_accuracy_m: 50.0` to `config/sensors/sensor_2.yaml`
      (depends on T004).
- [ ] T008 [P] Add `max_clock_offset_s: 0.5`, `min_alt_m: 0.0`, `max_alt_m: 200.0` to
      `config/scenarios/example_scenario.yaml`, with a comment saying these are system acceptance
      limits a sensor config cannot loosen (depends on T005).
- [ ] T009 [P] Update every `SensorConfig(`/`ScenarioConfig(` construction site in
      `tests/test_detections.py` to pass the six new required fields with values that satisfy the
      validators (depends on T005).
- [ ] T010 [P] Same as T009 for `tests/test_adapters.py` (depends on T005).
- [ ] T011 [P] Same as T009 for `tests/test_adapter_extensibility.py` (depends on T005).
- [ ] T012 In `tests/test_config_loader.py`, update existing construction sites and add validator tests:
      `min_hz > update_rate_hz`, `update_rate_hz > max_hz`, `accuracy_m > max_accuracy_m`,
      `min_alt_m >= max_alt_m`, target altitude outside bounds (each rejected with a
      `pytest.raises(match=...)` on the message), boundary-equal values accepted, and both example
      YAMLs load (depends on T005–T008).
- [ ] T013 [P] Create `src/conformance/results.py`: frozen pydantic `CheckResult` (`number` 1–7,
      `name` from the 7 canonical names, `passed`, `reason` non-empty with no newline) and
      `HarnessResult` (`sensor_id`, `checks` exactly 7 numbered 1–7 in order, computed `admitted`),
      per data-model.md.
- [ ] T014 [P] Create `src/conformance/probes.py`: `probe_position` (sensor position — configured
      `lat`/`lon`, else defended-area center — offset `range_m / 2` east via
      `src.simulator.geo.offset_to_latlon`, altitude `(min_alt_m + max_alt_m) / 2`);
      `withheld_tick_indices` (contiguous run of `ceil(2 × heartbeat_timeout_s × update_rate_hz)`
      ticks from index `n // 3`, clamped so ≥1 tick is supplied before and after);
      `build_probe_stream(sensor, scenario, withheld=frozenset())` → one `RawDetection` per
      non-withheld `expected_ticks` tick. No RNG (research.md R3; depends on T005).
- [ ] T015 Create `tests/test_conformance_checks.py` with probe tests: a round-trip test
      (`distance_m` from the sensor to `probe_position` equals `range_m / 2` within 1e-6 relative);
      probe inside check-3 and check-2 bounds; full probe length equals `len(expected_ticks(...))`;
      gap run length and clamping for a short schedule; two builds byte-identical (depends on T014).
      Also add a `CheckResult` validator test (an empty or multi-line reason is rejected; depends
      on T013).

**Checkpoint**: Config limits, result types, and probes exist; existing suite green.

---

## Phase 3: User Story 3 — Every check is independently provable (P1)

**Goal**: Seven pure check functions in `src/conformance/checks.py`, each with a passing and a
failing fixture exercised directly (SC-003).

**Independent Test**: `pytest tests/test_conformance_checks.py`; each check passes its good
evidence and fails its bad evidence with a fault-specific, single-line reason.

All tasks edit the same two files, so they run sequentially. Each task implements one check per
contracts/harness-api.md and adds its pass and fail fixtures to `tests/test_conformance_checks.py`.

- [ ] T016 [US3] `check_schema(messages)`: re-validate `Detection`/`Heartbeat` instances via
      `type(m).model_validate(m.model_dump())`; any other type FAILS; zero `Detection`s FAILS with
      "no Detections to evaluate". The FAIL reason names the first offending message (its index in
      the evaluated stream and its `detection_id`, if any) and the first failing field. Fail
      fixtures: a `Detection` produced by `model_copy(update={"confidence": 1.5})` (reason must
      contain `confidence`), plus a plain `dict` message (FR-002, R8).
- [ ] T017 [US3] `check_units(detections, sensor, scenario)`: FAIL if any `alt_m` is outside
      `[min_alt_m, max_alt_m]` or any `accuracy_m > max_accuracy_m`; the reason names the
      `detection_id`, the value, and the bound. Zero `Detection`s FAILS with "no Detections to
      evaluate" (spec Edge Cases). Fail fixtures: the drone's 120 m reported in feet (393.7), and an
      empty list. Boundary-equal values PASS (FR-003).
- [ ] T018 [US3] `check_coordinate_frame(detections, sensor, scenario)`: FAIL if
      `distance_m(sensor_pos, det) > range_m + 6 × accuracy_m`. Zero `Detection`s FAILS with "no
      Detections to evaluate" (spec Edge Cases). Known-answer test: 1° latitude north of the sensor =
      111,195 m — the published length of one degree of arc on a sphere of the IUGG mean Earth radius
      R₁ = 6,371.0 km (π/180 × R₁); cite this source in the test docstring. FAIL with
      `range_m` = 100,000 / `accuracy_m` = 1, PASS with `range_m` = 111,200. Fail fixtures: swapped
      lat/lon, sign-flipped lon, empty list (FR-004, R4).
- [ ] T019 [US3] `check_clock_offset(runs, scenario)`: per run, sorted references
      `start_utc + raw.t_s` vs sorted `Detection.timestamp_utc`; FAIL on count mismatch or worst
      |diff| > `max_clock_offset_s`; reason gives magnitude (3 decimals), direction ("ahead"/
      "behind"), and the limit; FAIL if there are zero pairs across all runs. Known-answer test:
      `t_s` [0, 0.5, 1.0], `start_utc` 1,735,689,600, outputs +2.0 s → reason contains
      "2.000 s ahead". Diff exactly equal to the limit PASSES (FR-005, R2).
- [ ] T020 [US3] `check_update_rate(full_probe_detections, sensor)`:
      `rate = (n − 1) / (t_last − t_first)`; FAIL if `n < 2` or the rate is outside
      `[min_hz, max_hz]`. Known-answer test: 11 detections 0.5 s apart = 2.0 Hz. Fail fixture:
      half-rate timestamps. A constant offset leaves the result unchanged (FR-006, R7).
- [ ] T021 [US3] `check_heartbeat(full_probe_messages, sensor, scenario)`: sort by `timestamp_utc`;
      FAIL if any consecutive gap > `heartbeat_timeout_s` or
      `(scheduled_span − output_span) > heartbeat_timeout_s`. Fail fixtures: a silent mid-stream run,
      and a stream that stops early. Gap exactly equal to the timeout PASSES; a constant offset leaves
      the result unchanged (FR-007, R7).
- [ ] T022 [US3] `check_dropped_messages(gap_probe_messages, supplied_count, withheld_count)`: FAIL if
      the `Detection` count ≠ `supplied_count`, the `Heartbeat` count ≠ `withheld_count`, or any
      `detection_id` is duplicated. Fail fixtures: a skipped Heartbeat, a fabricated Detection, a
      duplicate ID (FR-009, R1).

**Checkpoint**: All 7 checks are proven in isolation.

---

## Phase 4: User Story 1 — A known-good adapter is admitted (P1) 🎯 MVP

**Goal**: The harness runs an adapter on real, full-probe, and gap-probe inputs, and the gate
admits sensors 1 and 2 in under 60 s.

**Independent Test**: `pytest tests/test_conformance_harness.py -k known_good`.

- [ ] T023 [US1] Create `src/conformance/harness.py`: `run_harness(adapter, sensor, scenario,
      real_raw) -> HarnessRun` (`result`, `real_detections`). It calls `adapter` on real, full probe,
      and gap probe inputs, each call wrapped so an exception makes every dependent check FAIL with
      `adapter raised <Type>: <first line>`. It wraps each check call (an unexpected exception → that
      check FAILS only). It routes evidence per research.md R3: checks 1–4 over all runs, 5–6 full
      probe, 7 gap probe. Type `adapter` with `SensorAdapter` from `src.adapters.base` (FR-008,
      FR-010, FR-012; depends on T016–T022).
- [ ] T024 [US1] Create `src/conformance/gate.py`: `ConformanceGate` with `submit(...)` (runs the
      harness; replaces any prior entry for that `sensor_id`; stores the real-stream `Detection`s),
      `admitted_detections(sensor_id)` (stored `Detection`s if admitted, else `[]`, never
      `Heartbeat`s), and `results()` (latest per sensor, submit order) (FR-011; depends on T023).
- [ ] T025 [US1] Create `tests/test_conformance_harness.py`: build the real streams with
      `src.simulator.scenario.run_simulation` on the example scenario and both sensor YAMLs; submit
      `src.adapters.sensor1`/`sensor2` to a `ConformanceGate`; assert all 7 checks PASS for each,
      both are admitted, `admitted_detections` is non-empty and contains only `Detection`s. Assert
      total wall-clock < 60 s via `time.perf_counter`, measured from **before** `run_simulation`
      (generating the real streams counts toward the budget) through both `submit` calls (SC-001,
      SC-005, FR-014; depends on T024).

**Checkpoint**: The MVP gate admits the known-good adapters.

---

## Phase 5: User Story 2 — A non-conformant adapter is blocked with a specific reason (P1)

**Goal**: A clock-offset fault fails check 4 only, and the gate exposes none of that adapter's
`Detection`s until it is fixed and re-submitted.

**Independent Test**: `pytest tests/test_conformance_harness.py -k offset tests/test_conformance_gate.py`.

- [ ] T026 [US2] In `tests/test_conformance_harness.py`, add a local `offset_adapter` fixture that
      wraps `base.translate` and adds +2.0 s to every message's `timestamp_utc` (`Detection` and
      `Heartbeat`, via `model_copy`). Assert that check 4 FAILS with a reason containing the measured
      offset and "0.5", checks 1–3 and 5–7 PASS, and the result is not admitted (SC-002; depends on
      T025).
- [ ] T027 [US2] Create `tests/test_conformance_gate.py`. (a) Stub-fusion test: a `StubFusion`
      consumer ingests `gate.admitted_detections(id)` for every submitted sensor; it receives 0
      detections from the offset adapter and > 0 from sensor 1 (SC-004). (b) Re-admit: re-submitting
      the same sensor with the fixed adapter flips the verdict to admitted and releases its
      detections. (c) An adapter that raises is blocked, and its reason names the exception.
      (d) An unknown `sensor_id` returns `[]` (FR-011, US2 #2–#3; depends on T024, T026's fixture —
      define it in a shared `tests/conformance_fixtures.py` if both files need it).

**Checkpoint**: The gate blocks and re-admits; the demo's §10 narrative is testable.

---

## Phase 6: User Story 4 — Human-readable conformance report (P2)

**Goal**: A deterministic Markdown report with 7 rows per adapter and one-line reasons.

**Independent Test**: `pytest tests/test_conformance_report.py`.

- [ ] T028 [US4] Create `src/conformance/report.py`: `render_markdown(results)` → per result a
      `## <sensor_id> — ADMITTED|BLOCKED` heading and a `| # | Check | Result | Reason |` table with 7
      rows, `|` escaped in reasons, and no timestamps (FR-013, R10; depends on T013).
- [ ] T029 [US4] Create `tests/test_conformance_report.py`: render sensor 1 (admitted) and the offset
      adapter (blocked); assert 7 rows per adapter, PASS/FAIL tokens, a non-empty single-line reason
      per row, the verdict headings, `|` escaping, and byte-identical output across two renders
      (SC-006; depends on T028, T026's fixture).

---

## Phase 7: Polish & cross-cutting

- [ ] T030 Update `docs/architecture.md` per plan.md "Architecture doc update": a one-line §4 pointer
      to `specs/007-conformance-harness/`; minimal rewording of §4 check 3 (sensor coverage circle)
      and check 7 (adapter-side gap response, fusion coasting verified in #9); strike the four §13
      bullets assigned to #7 with one "Resolved in #7" pointer line. Do not touch §12.
- [ ] T031 Run `ruff check . && lint-imports && pytest`. All green. Re-run the three import probes
      (T003) and confirm no probe files remain. Save the exact output for the PR body.
- [ ] T032 Commit (imperative summary, why, `#7`, Co-authored-by trailer). Open the PR
      `feature/7-conformance-harness` → `main` with the PR-body requirements listed in plan.md (first
      line classification, analyze table, Architecture doc section noting the §4 check 3/7 changes,
      import probes (re-run from T003), check outputs). Confirm CI is green.
- [ ] T033 Request the independent review: `gh pr edit <N> --add-reviewer "@copilot"`. Address or
      dismiss (with reasoning) every finding, re-run T031, and record the outcome in the PR body.

---

## Dependencies & Execution Order

```text
Phase 1 (T001→T002→T003)   # verifies #26 / PR #27 merged; no edits
   ↓
Phase 2 (T004→T005 → {T006,T007,T008,T009,T010,T011} → T012; T013, T014 → T015)
   ↓
Phase 3 US3 (T016→…→T022)
   ↓
Phase 4 US1 (T023→T024→T025)  ── MVP
   ↓
Phase 5 US2 (T026 → T027)          Phase 6 US4 (T028 after T013; T029 after T026)
   ↓                                  ↓
Phase 7 (T030 → T031 → T032 → T033)
```

- US3 blocks US1 (the harness composes the checks). US1 blocks US2 (needs gate + harness). US4's
  renderer needs only T013, but its test reuses US2's offset fixture.

## Parallel Opportunities

- Phase 2: T006/T007/T008 (three YAMLs) and T009/T010/T011 (three test files) in parallel;
  T013 ∥ T014.
- Phase 5/6: T028 (report module, needs only T013) ∥ T026/T027. T027 is not `[P]` because it
  reuses T026's fixture.

## Implementation Strategy

1. **MVP** = Phases 1–4: checks proven and the gate admits sensors 1 and 2 in < 60 s.
2. **Demo-ready** = + Phase 5: the clock-offset fault is blocked with a specific reason and
   re-admitted after the fix.
3. **Evidence-ready** = + Phase 6: the Markdown report for the test record (#13).
4. Phase 7 then closes Principle I (architecture.md) and III (CI + independent review).
