# Feature Specification: Sensor 3 adapter with an injected clock-offset bug

**Feature Branch**: `feature/8-sensor3-clock-offset`

**Created**: 2026-11-01

**Status**: Draft

**Input**: Issue #8: "Third sensor adapter with injected timestamp offset bug (demo twist)".
Implement a third adapter on the same `SensorAdapter` contract as adapters 1 and 2, with a toggle
that injects (and can later remove) a timestamp offset larger than the harness's
`max_clock_offset_s`, to drive the demo's "add sensor live → harness fails → fix → harness passes"
beat (architecture.md §4 check 4, §10 sensor-3 flow).

## Why this is unsettled

Classified **unsettled** under `.github/copilot-instructions.md` triage rules 3 and 4:

- **Rule 3**: architecture.md §2–§11 do not pin down where the offset toggle lives, what form it
  takes, the offset's size and sign, or sensor 3's own configuration. §2's package layout only
  hints that per-sensor YAML may carry "offsets".
- **Rule 4**: two competent engineers could build materially different designs from the issue: a
  general-purpose offset field on the shared `SensorConfig` that any sensor's YAML could set,
  versus a bug that lives only in sensor 3's adapter code and is removed by editing that code.

Rules 1 and 2 do not fire. No §13 question is resolved, and no §12 row is touched.

## Clarifications

### Session 2026-11-01

- Q: What is the toggle, and what does "the fix" change? (Issue #8 says "flipping the config
  toggle"; the maintainer requires that the fix change adapter code.) → A: Option C. Sensor 3's
  adapter module exports two callables, `translate_with_clock_bug` (buggy) and `translate`
  (fixed). The demo toggle is which callable the caller submits; wiring that choice into the run
  config is #13's job (noted on #13). Tests cover both: buggy → BLOCKED with only check 4
  failing; fixed → ADMITTED; re-submitting fixed after buggy flips the gate verdict.
- Q: Offset size and sign? → A: Fixed +18.0 s ahead, modelling a sensor that reports GPS time
  labelled as UTC (GPS − UTC = 18 s). Constant `GPS_UTC_OFFSET_S` with a comment citing that;
  the fixed adapter subtracts it (amended after PR #30 review: the fixed adapter removes the
  offset by reporting UTC directly, not by float subtraction; see FR-008). Guard test: fails if the offset is ≤ the example scenario's
  `max_clock_offset_s`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Sensor 3 with the bug is blocked by the clock-offset check alone (Priority: P1)

As the demo operator, when I plug in sensor 3 with its timestamp bug present, I need the
conformance gate to block it, and the report to say specifically that the timestamps are off by
more than the allowed limit. No other check may fail, because a spurious second failure would
muddy the demo's one-cause, one-fix story.

**Why this priority**: This is the demo beat the issue exists for (§10: "Harness-->>A3: FAIL
(timestamp/clock-offset check)"). Without it there is no demo twist.

**Independent Test**: Run the conformance harness on sensor 3's adapter with the bug present,
against sensor 3's real simulated stream. Exactly check 4 fails, the gate releases no sensor-3
`Detection`s, and the check-4 reason states the measured offset, its direction and the limit.

**Acceptance Scenarios**:

1. **Given** sensor 3's adapter with the bug present and the example scenario, **When** it is
   submitted to the gate, **Then** the verdict is BLOCKED, check 4 FAILS, and checks 1–3 and
   5–7 PASS.
2. **Given** that blocked verdict, **When** a downstream consumer asks the gate for sensor 3's
   `Detection`s, **Then** it receives none.
3. **Given** that blocked verdict, **When** the Markdown report is rendered, **Then** sensor 3's
   section shows BLOCKED, and its check-4 row gives the measured offset and the
   `max_clock_offset_s` limit.

---

### User Story 2 - Removing the bug makes sensor 3 pass all 7 checks (Priority: P1)

As the demo operator, after the bug is fixed I need a re-run to admit sensor 3 on all 7 checks,
with no change to any scenario-level acceptance limit, so the audience sees the adapter fixed
rather than the bar lowered.

**Why this priority**: This is the "fix → harness passes" half of the demo beat and an explicit
issue acceptance criterion. A pass obtained by loosening `max_clock_offset_s` would be a false
demo.

**Independent Test**: Run the harness on sensor 3's fixed adapter with the same, unmodified
example scenario. All 7 checks pass, the verdict is ADMITTED, and the gate releases exactly one
`Detection` per raw input in sensor 3's real stream.

**Acceptance Scenarios**:

1. **Given** sensor 3 with the bug removed, **When** it is submitted to the gate with the
   unmodified example scenario, **Then** all 7 checks PASS and the verdict is ADMITTED.
2. **Given** the admitted verdict, **When** a downstream consumer asks for sensor 3's
   `Detection`s, **Then** it receives one per raw input in sensor 3's real stream, with
   `timestamp_utc` equal to `start_utc + t_s`.
3. **Given** the fail → fix sequence, **When** the scenario configuration is compared before and
   after, **Then** every `ScenarioConfig` value, including `max_clock_offset_s`, is identical.

---

### User Story 3 - The full fail → fix → pass sequence is proven by an automated test (Priority: P1)

As the maintainer, I need one automated test that runs the whole sequence on a single gate:
submit sensor 3 with the bug (blocked), fix it, re-submit (admitted). Then the demo beat is
guaranteed by CI, not by a manual rehearsal.

**Why this priority**: An explicit issue acceptance criterion ("demonstrates the full fail → fix →
pass sequence programmatically").

**Independent Test**: The test itself. It is green only if the first submission is BLOCKED by
check 4 alone and the second is ADMITTED on all 7 checks for the same sensor id on the same
gate.

**Acceptance Scenarios**:

1. **Given** one gate, **When** `translate_with_clock_bug` is submitted for sensor 3 and then
   `translate` is re-submitted, **Then** the first verdict is BLOCKED (check 4 only), the second
   is ADMITTED, and the re-submission flips the gate's single verdict for sensor 3 from BLOCKED
   to ADMITTED.
2. **Given** the same sequence, **When** sensors 1 and 2 are also submitted, **Then** their
   verdicts are ADMITTED and unchanged by sensor 3's fail → fix.

---

### Edge Cases

- **Offset exactly equal to the limit**: check 4's limit is inclusive (#7, FR-005), so an offset
  of exactly `max_clock_offset_s` would PASS. The injected offset must be strictly larger than
  the limit; a test must prove that an offset equal to the limit does not trigger the demo
  failure.
- **Offset applied to `Detection`s only**: #7 recorded that a constant offset on `Detection`s
  but not `Heartbeat`s fails check 7 as well as check 4 (plan.md "Accepted limitation (partial
  clock offset)"). The bug MUST shift every emitted message's `timestamp_utc`, so the demo fails
  check 4 alone.
- **Offset sign**: a clock running ahead ("in the future") and one running behind ("stale") both
  fail check 4. The demo uses one fixed direction (+18 s ahead, FR-008) so its report wording is
  predictable.
- **Sensor 3 sees no target for the whole run**: checks 1–4 still have probe-stream `Detection`s
  (#7, FR-008), so the bug is still caught.
- **Fix done by loosening the limit**: forbidden. A test asserts the scenario used in the fixed
  run is the unmodified example scenario.
- **Adding sensor 3 to a simulation run must not change sensors 1 and 2's streams**: per-sensor
  RNG streams are spawned by index, so sensor 3 is appended after them (Principle V).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A sensor-3 adapter MUST implement the existing `SensorAdapter` contract unchanged
  (same call signature, emitting `Detection | Heartbeat`), reusing the shared translation from
  #6 rather than duplicating it.
- **FR-002**: Sensor 3 MUST have its own sensor configuration with a distinct `sensor_id` and
  values that pass every existing `SensorConfig` validator, so the only fault the harness can
  find is the injected offset.
- **FR-003**: With the bug present, the sensor-3 adapter MUST add the same constant offset to the
  `timestamp_utc` of **every** message it emits, `Detection`s and `Heartbeat`s alike, so only
  check 4 is affected (#7 FR-009a).
- **FR-004**: The injected offset MUST be strictly greater in magnitude than the example
  scenario's `max_clock_offset_s`. A test MUST fail if the offset is reduced to the limit or
  below, or if the limit is raised to the offset or above.
- **FR-005**: Sensor 3's adapter module MUST export two `SensorAdapter` callables: a buggy one
  (`translate_with_clock_bug`) and a fixed one (`translate`). The demo "toggle" is which callable
  the caller submits to the gate; the fix is adapter code (the fixed callable removes the
  offset), never configuration. Sensor 3's YAML MUST NOT carry an offset field, and the fix MUST
  NOT change any `ScenarioConfig` value. Wiring the choice into the run configuration is #13's
  job.
- **FR-006**: With the bug removed, the sensor-3 adapter's output MUST be identical to the
  shared translation's output for the same inputs, so sensor 3 passes all 7 checks under the
  unmodified example scenario.
- **FR-007**: An automated test MUST run the fail → fix → pass sequence on one gate: BLOCKED with
  only check 4 failing, then ADMITTED with all 7 passing. The check-4 FAIL reason MUST give the
  measured offset, its direction and the limit (Principle VI).
- **FR-008**: The injected offset MUST be a fixed +18.0 s (ahead), held in a named constant
  `GPS_UTC_OFFSET_S` whose comment states that it models a sensor reporting GPS time labelled as
  UTC (GPS − UTC = 18 s). The buggy callable models the sensor's raw clock (+18 s on every
  message); the fixed callable removes `GPS_UTC_OFFSET_S` and reports UTC. A guard test MUST fail
  if `GPS_UTC_OFFSET_S` is ≤ the example scenario's `max_clock_offset_s` (FR-004).
  The GPS clock is modelled inside sensor 3's adapter, not in the simulator: the simulated raw
  stream stays truth-aligned (FR-009, FR-010), the buggy callable labels the sensor's clock
  reading (UTC + `GPS_UTC_OFFSET_S`) as UTC, and the fixed callable reports UTC directly. It
  MUST NOT recover UTC as `(utc + GPS_UTC_OFFSET_S) − GPS_UTC_OFFSET_S`, because that round trip
  is not exact where adding 18 s crosses a float64 binade, which would break FR-006 (PR #30
  review finding).
- **FR-009**: Adding sensor 3 MUST NOT change the conformance harness, the `SensorAdapter`
  contract, the `Detection`/`Heartbeat` schemas, the simulator, or any `ScenarioConfig` limit
  (Principle IV; §3's "one adapter module + one config entry" extensibility claim).
- **FR-010**: Sensor 3's real simulated stream MUST be produced by the existing simulator with
  sensor 3 appended after sensors 1 and 2, so their streams are unchanged (Principle V).

### Key Entities

- **Sensor-3 configuration**: a sensor configuration like sensors 1 and 2's (id, accuracy,
  range, rate band, heartbeat timeout, accuracy limit, position), validated by the existing
  rules.
- **Sensor-3 adapter**: a module exporting two `SensorAdapter` callables that reuse the shared
  translation: `translate_with_clock_bug`, which shifts every message's timestamp by the
  injected offset, and `translate`, which does not.
- **Clock-offset bug toggle**: the choice between the two exported callables (FR-005). The
  offset is the constant `GPS_UTC_OFFSET_S` (FR-008).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With the bug present, sensor 3 fails exactly 1 of 7 checks (check 4) and 0
  sensor-3 `Detection`s are released by the gate.
- **SC-002**: With the bug removed, sensor 3 passes 7 of 7 checks and the gate releases 100% of
  sensor 3's real-stream `Detection`s, one per raw input.
- **SC-003**: The fail → fix → pass sequence runs in one automated test, under the same 60 s
  budget the harness already meets for two sensors (#7 SC-005).
- **SC-004**: Between the failing and passing runs, 0 `ScenarioConfig` values change.
- **SC-005**: Sensors 1 and 2's raw streams and verdicts are identical with and without sensor 3
  in the run.

## Assumptions

- Sensor 3 gets its own YAML in `config/sensors/` with distinct, realistic values, following
  the sensor 1 and 2 pattern. Its position and parameters are chosen so it covers the scenario's
  drone, contributing to §10's "improved picture, 3 sensors" once admitted.
- The bug models a sensor clock skew: one constant offset on every timestamp. It is not jitter
  or drift, which would also fail checks 5–7 and break the "check 4 only" acceptance criterion.
- Live toggling during a running demo, and the `sensor_id` → adapter lookup, belong to #13
  (orchestration; architecture.md §13's open bullet). #8 delivers the adapter, its config, the
  toggle and the programmatic fail → fix → pass test.
- No change to the harness (#7) is needed. Its clock-offset fixture already shows a constant
  +2.0 s offset fails check 4 alone.
