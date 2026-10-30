# Tasks: Sensor adapter contract (Detection schema + 2 known-good adapters)

**Input**: Design documents from `specs/006-sensor-adapter-contract/` (spec.md, plan.md)

**Prerequisites**: plan.md (required, 6 rubber-duck review rounds complete), spec.md (required)

**Tests**: Included — not strict test-first/TDD (write-tests-first is not adopted project-wide
per the user's explicit decision), but every user story phase adds its own test coverage
alongside/after its implementation, consistent with the project's existing test style
(`tests/test_detections.py`, `tests/test_trajectories.py`) and constitution Principle III
(test-first & CI-gated — tests must exist and pass before merge, not necessarily be written
chronologically first).

**Organization**: Tasks are grouped by user story (spec.md US1/US2/US3) to enable independent
implementation and testing of each story, per spec-kit convention.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3) — Setup/Foundational/Polish
  tasks have no story label
- File paths are exact, per plan.md's Project Structure section

## Path Conventions

Single Python project; `src/`, `tests/`, `config/` at repository root (existing layout).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Land the one pre-existing-code change this issue needs, in its own isolated,
independently verifiable commit (disposition item 35's explicit sequencing requirement).

- [ ] T001 Extract `expected_ticks(update_rate_hz: float, duration_s: float) -> list[float]` out
      of the formula currently inlined in `generate_sensor_detections` in
      `src/simulator/detections.py` (the `math.floor(duration_s/dt_s)+1` / `min(i*dt_s,
      duration_s)` logic), with zero behavior change — `generate_sensor_detections` must call the
      new helper and produce byte-identical output. Verify the existing `tests/test_detections.py`
      suite passes **unmodified** before any task in Phase 2 touches that file (plan.md
      disposition items 15, 35).

**Checkpoint**: `expected_ticks()` is available for both the simulator and the new adapter code to
import and share — no duplicated tick-schedule formula.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core schema, config fields, and protocol shape every user story depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T002 [P] Create `Detection` and `Heartbeat` pydantic models in `src/adapters/messages.py`
      per architecture.md §3.1 and spec.md's Key Entities: `Detection(sensor_id: str,
      detection_id: str, timestamp_utc: float, lat: float, lon: float, alt_m: float,
      accuracy_m: PositiveFloat, velocity_mps: float | None, confidence: float | None,
      raw_payload: dict)`; `Heartbeat(sensor_id: str, timestamp_utc: float, t_s: float)` with
      `t_s` documented as informational/debugging only (FR-001, FR-006, Key Entities).
- [ ] T003 [P] Extend `src/config/models.py`: add `heartbeat_timeout_s: PositiveFloat` to
      `SensorConfig`, with a model validator enforcing `heartbeat_timeout_s >
      1 / update_rate_hz` at construction time (strict `>`, not `>=` — disposition item 32); add
      `start_utc: NonNegativeFloat` to `ScenarioConfig`, required with no default (FR-007, FR-008).
- [ ] T004 [P] Update `config/sensors/example_sensor.yaml` to add a valid `heartbeat_timeout_s`
      value to the existing `sensor-1` entry (depends on T003).
- [ ] T005 [P] Update `config/scenarios/example_scenario.yaml` to add a valid `start_utc` value
      (depends on T003).
- [ ] T006 [P] Update `tests/test_detections.py`'s fixtures to pass `heartbeat_timeout_s` and
      `start_utc` explicitly on every `SensorConfig`/`ScenarioConfig` construction site in that
      file (depends on T003) — no defaults exist to fall back on (disposition item 35).
- [ ] T007 Define the `SensorAdapter` protocol in `src/adapters/base.py`:
      `translate(raw_detections: list[RawDetection], sensor: SensorConfig,
      scenario: ScenarioConfig) -> list[Detection | Heartbeat]` (signature only at this stage;
      depends on T002).

**Checkpoint**: Foundation ready — schema, config, and protocol shape exist; user story
implementation can now begin.

---

## Phase 3: User Story 1 - Sensor 1 and sensor 2 feed valid detections into the pipeline (Priority: P1) 🎯 MVP

**Goal**: `translate()` converts every in-schedule `RawDetection` into a valid, correctly-unit-
converted `Detection`, for both sensor 1 and sensor 2, with no fabricated optional fields.

**Independent Test**: Run each adapter against a `RawDetection` stream from
`src/simulator/detections.py` for that sensor, and confirm every resulting object is a valid
`Detection` per architecture.md §3.1 (spec.md's Independent Test for US1).

### Implementation for User Story 1

- [ ] T008 [US1] Implement `translate()`'s Detection-emission logic in `src/adapters/base.py`:
      for each `RawDetection`, raise if `raw.t_s` is not exactly a value from
      `expected_ticks(sensor.update_rate_hz, scenario.duration_s)` (FR-010), raise if
      `raw.sensor_id != sensor.sensor_id` (FR-011), otherwise emit a `Detection` with
      `detection_id = f"{sensor.sensor_id}:{tick_index}:{index_within_tick}"` (FR-009),
      `timestamp_utc = scenario.start_utc + raw.t_s`, `sensor_id` always from
      `sensor.sensor_id` (never copied from `raw`, per FR-011), `lat`/`lon`/`alt_m` passed through,
      `accuracy_m` from `sensor.accuracy_m`, `velocity_mps`/`confidence` left `None` (not
      fabricated), `raw_payload = raw.model_dump()` (depends on T001, T003, T007). (Heartbeat
      emission for unmatched ticks is deferred to US3, Phase 5 — not part of this task.)
- [ ] T009 [P] [US1] Create `src/adapters/sensor1.py`: re-export `base.translate` alongside
      sensor 1's `SensorConfig` loaded from `config/sensors/example_sensor.yaml` (depends on T008).
- [ ] T010 [P] [US1] Create `config/sensors/sensor_2.yaml` — a real, distinct `SensorConfig` for
      sensor 2 (its own `update_rate_hz`, `accuracy_m`, and position — not a copy of sensor 1's;
      disposition item 30).
- [ ] T011 [US1] Create `src/adapters/sensor2.py`: re-export `base.translate` alongside sensor 2's
      `SensorConfig` loaded from `config/sensors/sensor_2.yaml` (depends on T008, T010).
- [ ] T012 [US1] Add schema-conformance and unit-correctness tests to `tests/test_adapters.py`:
      both adapters produce 100% valid `Detection` objects (SC-001), `alt_m`/`accuracy_m` units
      correct, `timestamp_utc == scenario.start_utc + raw.t_s`, `velocity_mps`/`confidence` are
      `None` when absent from `RawDetection`, `detection_id` format/uniqueness across multiple
      same-tick detections (FR-009), off-schedule `t_s` raises (FR-010), mismatched `sensor_id`
      raises (FR-011) (depends on T009, T011).

**Checkpoint**: User Story 1 is independently functional and testable (Detection-only behavior;
heartbeat/schedule-coverage is US3's addition on top of this).

---

## Phase 4: User Story 2 - A new sensor can be added without touching contract/simulator code (Priority: P1)

**Goal**: Prove the `SensorAdapter` interface alone is sufficient to add a third sensor, with zero
changes to `src/simulator/`, the `Detection`/`Heartbeat` schemas, or sensor 1/2's adapters.

**Independent Test**: Write a throwaway third test adapter implementing `SensorAdapter` and
confirm it produces valid `Detection` objects with no changes elsewhere (spec.md's Independent
Test for US2).

### Implementation for User Story 2

- [ ] T013 [P] [US2] Write `tests/test_adapter_extensibility.py`: construct a throwaway third
      `SensorConfig` locally in the test file (no new file under `src/adapters/`), call
      `base.translate` directly against it and a hand-built `RawDetection` stream, and assert
      valid `Detection` output with zero changes to `src/simulator/`, `src/adapters/messages.py`,
      `src/adapters/base.py`'s `translate` signature, or `sensor1.py`/`sensor2.py` (SC-002)
      (depends on T008; independent of T009-T012's files, so can run in parallel with Phase 3's
      adapter-file tasks once T008 lands).

**Checkpoint**: User Stories 1 and 2 both work independently — extensibility is proven by an
actual test, not asserted.

---

## Phase 5: User Story 3 - A sensor's schedule-coverage is observable (Priority: P2)

**Goal**: Every scheduled tick produces either a `Detection` or an explicit `Heartbeat` — no tick
is silently unaccounted for — satisfying architecture.md §3.4's heartbeat/liveness-signal wording
at the schedule-coverage scope this issue honestly claims (not real sensor-failure detection; see
spec.md's Scope note and plan.md's Known limitation).

**Independent Test**: Run an adapter across ticks where its truth object is out of range, and
confirm a `Heartbeat` is produced at the sensor's configured cadence for each such tick, without a
fabricated `Detection` (spec.md's Independent Test for US3).

### Implementation for User Story 3

- [ ] T014 [US3] Extend `translate()` in `src/adapters/base.py`: compute
      `expected_ticks(sensor.update_rate_hz, scenario.duration_s)`, assert the returned ticks are
      unique before using them as a lookup key (defensive assertion per plan.md's final note), and
      for every scheduled tick with no validated matching `RawDetection`, emit a
      `Heartbeat(sensor_id=sensor.sensor_id, timestamp_utc=scenario.start_utc + t_s, t_s=t_s)`
      instead of leaving the tick unaccounted for (FR-006) (depends on T008).
- [ ] T015 [US3] Add heartbeat/schedule-coverage tests to `tests/test_adapters.py`: every
      scheduled tick yields exactly one `Detection` or `Heartbeat` with none missing (SC-003),
      `Heartbeat` is emitted for ticks with no target in range and for dropped detections alike
      (both indistinguishable by design — plan.md disposition item 5), `Heartbeat.timestamp_utc`
      shares `Detection`'s time base, and the pre-existing final-tick-may-be-omitted quirk of
      `expected_ticks()`/`generate_sensor_detections` is preserved, not "fixed" (depends on T012,
      T014 — same test file as T012, land sequentially to avoid merge conflicts).

**Checkpoint**: All three user stories are independently functional; `translate()`'s full
contract (Detection + Heartbeat + validation) is complete.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Architecture-doc truth update (constitution Principle I) and merge readiness.

- [ ] T016 Update `docs/architecture.md` per plan.md's "Architecture doc update" section:
      §3.4 (reword to state schedule-coverage vs. real liveness, and drop "fusion engine" from the
      dead-sensor clause), §13 (strike the heartbeat bullet, add a "Resolved in #6" pointer plus
      the 5 new open-question bullets: `update_rate_hz` vs. `[min_hz, max_hz]` range, real-liveness
      gap for #7, the ruled-out `Detection | Heartbeat` cadence-check approach, the
      `raw_payload`/clock-offset-reference open question, and the `sensor_id`-to-adapter mapping
      open question), §2 (adapters package populated; add the `translate()` signature, `Heartbeat`
      shape, and new config fields as a "Resolved during implementation" note), §3.1
      (`detection_id` format note + `Heartbeat` field table) (depends on all of Phases 1-5).
- [ ] T017 [P] Run the full `pytest` suite and confirm zero regressions in
      `tests/test_trajectories.py`, `tests/test_scenario.py`, `tests/test_config_loader.py`, and
      the rest of the unmodified test suite, in addition to the new/updated tests above.
- [ ] T018 Request the sonnet-tier implementation/test review (per
      `.github/copilot-instructions.md`'s "Agent roles and model assignment": confirm tests
      actually exercise the implemented feature, then final verification) before opening the PR.
- [ ] T019 Open the PR for `feature/6-sensor-adapter-contract` → `main`, confirm CI passes, and
      flag it to the user for their manual merge approval (the new human-approval-gate process).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 (T006 specifically must follow T001's unmodified-
  suite verification) — BLOCKS all user stories.
- **User Stories (Phase 3-5)**: All depend on Foundational (Phase 2) completion.
  - US1 (P1) and US2 (P1) can proceed in parallel once T008 (the Detection-emission core) lands.
  - US3 (P2) extends the same `translate()` function US1 built, so it starts after T008 but can
    run concurrently with US2's extensibility test (different files).
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### User Story Dependencies

- **User Story 1 (P1)**: Starts after Foundational. No dependency on US2/US3.
- **User Story 2 (P1)**: Starts after T008 (US1's core `translate()` logic exists). Does not
  depend on US1's adapter-binding files (T009-T012) or on US3's heartbeat logic.
- **User Story 3 (P2)**: Starts after T008. Extends the same function US1 built; its tests
  (T015) land after US1's tests (T012) in the same file to avoid merge conflicts, not because of
  a functional dependency.

### Parallel Opportunities

- T002, T003 (Phase 2) — different files, no shared dependency.
- T004, T005, T006 (Phase 2) — different files, all depend only on T003.
- T009, T010 (Phase 3) — different files.
- T013 (US2) can run in parallel with T009-T012 (US1) once T008 is done.

---

## Parallel Example: Phase 2 (Foundational)

```bash
# Launch independent foundational tasks together:
Task: "Create Detection and Heartbeat models in src/adapters/messages.py"
Task: "Extend SensorConfig/ScenarioConfig in src/config/models.py"
```

## Parallel Example: User Story 1 adapter files

```bash
# Once T008 (translate() core) is done:
Task: "Create src/adapters/sensor1.py"
Task: "Create config/sensors/sensor_2.yaml"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational).
2. Complete Phase 3 (US1) — both sensors translate correctly.
3. **STOP and VALIDATE**: run `tests/test_adapters.py`'s US1 tests independently.
4. US1 alone is not yet mergeable (US2's extensibility proof and US3's heartbeat deliverable are
   both explicitly required by the issue), but it is the right order to validate incrementally.

### Incremental Delivery

1. Setup + Foundational → shared schema/config/protocol ready.
2. US1 → both concrete adapters translate `Detection`s correctly → validate independently.
3. US2 → extensibility proven by an actual throwaway-adapter test → validate independently.
4. US3 → heartbeat/schedule-coverage added on top of the same `translate()` → validate
   independently.
5. Polish → architecture.md updated, full suite green, sonnet-tier review, PR opened, human
   merge approval.

---

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps each task to spec.md's US1/US2/US3 for traceability.
- This feature's "independent story" model is looser than a typical CRUD feature: US1, US2, and
  US3 all extend the same single `translate()` function rather than three separate code paths —
  independence here means each story's *tests* and *observable behavior* are independently
  verifiable, not that the implementation is physically partitioned.
- Per constitution Principle III, the heartbeat/liveness logic (T014) and the config validator
  (T003) are non-trivial logic requiring the opus-tier rubber-duck review already completed on
  spec.md/plan.md, plus the sonnet-tier implementation review (T018) before merge.
- Commit after each task or logical group, consistent with plan.md's required commit boundaries
  (T001 standalone before T003-T006; T003 before T004-T006).
