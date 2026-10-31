# Feature Specification: Conformance harness (7 contract checks + pass/fail report)

**Feature Branch**: `feature/7-conformance-harness`

**Created**: 2026-10-31

**Status**: Draft

**Input**: GitHub issue [#7](https://github.com/onelcruz/plug-and-prove/issues/7), architecture.md §4 (The conformance harness)

## Why this is unsettled

Classified per `.github/copilot-instructions.md` "Before writing code", step 3:

- **Rule 1 fires**: architecture.md §13 explicitly assigns four open questions to #7 — (a)
  `SensorConfig`'s single `update_rate_hz` vs §3.4's `[min_hz, max_hz]` range; (b) real liveness
  evidence vs. #6's schedule-coverage `Heartbeat`; (c) how check 5 measures update rate once a
  sensor can produce `Heartbeat`-only stretches (measuring across `Detection | Heartbeat` is
  explicitly ruled out); (d) whether `raw_payload["t_s"]` becomes the load-bearing simulator-time
  reference for check 4.
- **Rule 3 fires**: §4 depends on thresholds that are not pinned down anywhere in §2–§11 or the
  config models: `max_clock_offset_s`, `[min_hz, max_hz]`, "plausible configured bounds" for
  `alt_m`/`accuracy_m`, the check-3 bounding box, and check 4's future/stale tolerances.

The locked decisions this feature must honor (not re-decide): §12 row 3 (harness is a
pre-ingest **gate**, not a passive monitor), §12 row 2 (in-process transport), §3.1 `Detection`
schema, §3.4/§5 (`Heartbeat` is harness-only; fusion consumes only post-gate `Detection`s).

## Clarifications

### Session 2026-10-31

- Q: How should check 7 ("dropped-message behavior") be scoped, given §4 defines it against the fusion engine's coasting behavior and the fusion engine (#9) doesn't exist yet? → A: C — check 7 is an adapter-side check: the harness removes raw inputs to create gaps and verifies the adapter does not crash, emits a `Heartbeat` for every gapped tick, and neither fabricates nor duplicates `Detection`s. Fusion-coasting verification moves to #9 (acceptance criterion added there). §4 check 7's wording is updated in architecture.md in this PR. The gate test uses a stub downstream consumer.
- Q: What should check 4 use as each `Detection`'s simulator reference time when measuring clock offset? → A: B — the harness's own inputs: reference times are `start_utc + raw.t_s` for every raw input the harness supplied, compared in sorted order against the sorted `Detection.timestamp_utc` values; a count mismatch FAILS with a reason. Resolves §13 bullet (d): `raw_payload["t_s"]` does not become load-bearing. Accepted limitation (recorded in plan.md): this only works because the harness supplies the inputs; a real networked sensor would need a different reference.
- Q: What raw input should the harness feed an adapter when evaluating it? → A: C — both. The harness generates deterministic probe streams (one raw input per scheduled tick at a fixed in-range position, plus gap variants); checks 1–4 run over everything the harness fed (probe + real scenario stream), checks 5–7 run on probe streams only, where the harness controls exactly which ticks have input. Resolves §13 bullets (b) (real gap evidence comes from harness-withheld ticks) and (c) (check 5 measures `Detection`-only rate on a probe stream where the target is always in view, so no `Heartbeat`-only stretch can occur).
- Q: What geographic bounds should check 3 (coordinate frame) enforce, given §4's literal "defended-area bounding box" would reject correct detections? → A: A — per-sensor coverage circle: a `Detection` FAILS if it is more than `range_m + 6 × accuracy_m` from the sensor's position (configured `lat`/`lon`, else the defended-area center). No new config fields. architecture.md §4 check 3 is reworded in this PR.
- Q: How should the new conformance limits be added to config? → A: A, modified — `min_hz`, `max_hz`, and `max_accuracy_m` are flat, required `SensorConfig` fields (validators: `min_hz ≤ update_rate_hz ≤ max_hz`, `accuracy_m ≤ max_accuracy_m`). `max_clock_offset_s`, `min_alt_m`, and `max_alt_m` are flat, required `ScenarioConfig` fields (validator: `min_alt_m < max_alt_m`): they are system acceptance limits, not sensor properties, and a sensor's own config must not set the bar it is tested against (otherwise #8's sensor 3 could pass by loosening its own tolerance). Resolves §13 bullet (a).
- Q (raised during `/speckit-plan`): How can the harness use `RawDetection`, `expected_ticks()`, and the `SensorAdapter` protocol when `src.simulator.detections` imports `trajectories` (an indirect ground-truth import that breaks `no-ground-truth-leak`)? → A: Move `detections.py`'s `TruthObject` import (annotation-only) under `if TYPE_CHECKING:` and set `exclude_type_checking_imports = True` in `.importlinter`; also re-add `src.adapters` to `no-ground-truth-leak` in this PR to offset the linter loosening. Disclosed as a Principle IV exception (one file outside `src/conformance/`, no behavior change).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A known-good adapter is admitted to the pipeline (Priority: P1)

As the orchestrator, I need to submit an adapter (with its sensor config) to the harness and
receive an explicit PASS before any of that adapter's `Detection`s are allowed downstream, so the
demo's "already-conformant sensors join the picture" step (§10) is enforced, not assumed.

**Why this priority**: Without the gate admitting sensors 1 & 2, nothing reaches fusion at all —
this is the baseline the rest of the demo stands on.

**Independent Test**: Run the harness against sensor 1's and sensor 2's adapters (#6) with the
example scenario; every one of the 7 checks reports PASS, the gate admits each adapter, and the
whole run finishes in under 60 seconds.

**Acceptance Scenarios**:

1. **Given** sensor 1's adapter and config, **When** the harness runs all 7 checks, **Then** every
   check reports PASS with a one-line reason, and the gate result is "admitted".
2. **Given** the same for sensor 2 (different rate/accuracy/position), **When** run, **Then** the
   same outcome — no check is tuned to one sensor only.
3. **Given** both known-good adapters, **When** the harness runs end to end, **Then** total
   wall-clock time is under 60 seconds.

### User Story 2 - A non-conformant adapter is blocked with a specific, explainable reason (Priority: P1)

As the demo operator, when sensor 3 is plugged in with an injected timestamp offset (#8), I need
the harness to fail **specifically** the timestamp/clock-offset check with a clear reason —
without false-failing the other six — and the gate to keep sensor 3's `Detection`s out of the
pipeline entirely.

**Why this priority**: This is the demo's central narrative beat (§4, §10) and an explicit epic
acceptance criterion; a passive or noisy harness defeats the SBIR claim.

**Independent Test**: Run the harness against a deliberately broken adapter fixture that adds a
constant offset to `timestamp_utc`; confirm check 4 FAILS with a reason naming the measured
offset and the configured limit, checks 1–3 and 5–7 PASS, and the gate exposes zero of that
adapter's `Detection`s to downstream consumers.

**Acceptance Scenarios**:

1. **Given** an adapter whose `timestamp_utc` is shifted beyond `max_clock_offset_s`, **When** the
   harness runs, **Then** check 4 FAILS, its reason states the measured offset and the limit, and
   all other checks PASS.
2. **Given** that failing result, **When** a downstream consumer asks the gate for admitted
   `Detection`s, **Then** it receives none from that adapter (gate, not monitor — §12 row 3).
3. **Given** the same adapter after the offset is corrected, **When** the harness is re-run,
   **Then** all checks PASS and the gate admits it (§10's "re-run → PASS → now trusted" step).

### User Story 3 - Every check is independently provable (Priority: P1)

As a reviewer, I need each of the 7 checks to have its own passing and failing fixture, so each
check is shown to actually detect the fault it names (not just to pass on good data).

**Why this priority**: Explicit acceptance criterion in #7; a check with no failing fixture is
unfalsifiable and provides no evidence.

**Independent Test**: For each check 1–7, run it alone against a minimal passing input and a
minimal input exhibiting exactly that fault; the check passes the former and fails the latter
with a reason specific to that fault.

**Acceptance Scenarios**:

1. **Schema** — a message missing a required field or with a wrong type FAILS; valid ones PASS.
2. **Units** — `alt_m` outside the scenario's `[min_alt_m, max_alt_m]` (e.g. feet reported as
   meters: 120 m reported as 394) or `accuracy_m` above the sensor's `max_accuracy_m` FAILS.
3. **Coordinate frame** — a `Detection` farther than `range_m + 6 × accuracy_m` from the sensor
   (e.g. swapped lat/lon, radians instead of degrees, sign-flipped longitude) FAILS.
4. **Timestamp / clock offset** — any `Detection` whose `timestamp_utc` is more than
   `max_clock_offset_s` ahead of ("future") or behind ("stale") its harness-known reference time
   FAILS.
5. **Update rate** — a measured rate outside the sensor's configured `[min_hz, max_hz]` FAILS.
6. **Heartbeat / liveness** — any gap between consecutive messages longer than
   `heartbeat_timeout_s`, or an output stream that stops early/starts late by more than
   `heartbeat_timeout_s`, FAILS.
7. **Dropped-message behavior** — with harness-injected gaps in the raw input, an adapter that
   crashes, emits a `Detection` count different from the raw inputs supplied, emits a `Heartbeat`
   count different from the withheld ticks, or duplicates a `detection_id` FAILS; an adapter that
   emits exactly one `Heartbeat` per withheld tick PASSES.

### User Story 4 - A human-readable conformance report (Priority: P2)

As the demo presenter and SBIR evidence author, I need a report listing each of the 7 checks as
PASS/FAIL with a one-line reason per sensor, so results are explainable on camera and can be
captured by the test record writer (#13/§9).

**Why this priority**: Required deliverable, but it renders results produced by P1 stories.

**Independent Test**: Generate the report for one passing and one failing adapter; confirm it
lists exactly 7 checks per adapter, each with PASS/FAIL and a single-line reason, plus an overall
admitted/blocked verdict.

**Acceptance Scenarios**:

1. **Given** a harness result set, **When** the report is generated, **Then** it is Markdown with
   one row per check (name, PASS/FAIL, one-line reason) and an overall verdict per adapter.
2. **Given** the same inputs twice, **When** the report is generated twice, **Then** the outputs
   are byte-identical (Principle V reproducibility; no wall-clock timestamps in the report body).

### Edge Cases

- An adapter that raises an exception mid-run: the harness must record a FAIL (with the exception
  summarized in the reason) and block the adapter, not crash the whole harness run.
- An adapter that returns zero messages: checks 5 and 6 FAIL (no evidence of cadence/liveness);
  checks 1–4 must not trivially PASS on an empty set without saying so — the reason must state
  "no Detections to evaluate" and the check result must be FAIL, since vacuous truth is not
  evidence of conformance.
- A sensor whose target is never in view for the whole real run (all `Heartbeat`s): checks 1–4
  still have probe-stream `Detection`s to evaluate, and checks 5–7 use probe streams only, so no
  check becomes vacuous.
- A check-4 offset exactly equal to `max_clock_offset_s`: PASS (limit is inclusive).
- Heartbeat gap exactly equal to `heartbeat_timeout_s`: PASS (inclusive).
- An adapter with only a constant clock offset: checks 5–7 are offset-invariant (FR-009a), so only
  check 4 FAILS.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The harness MUST implement exactly 7 checks, one per §4 item, each returning a
  structured result: check id/name, PASS/FAIL, and a one-line human-readable reason (Principle VI).
- **FR-002**: Check 1 (schema) MUST validate every emitted message against the canonical
  `Detection`/`Heartbeat` models and FAIL on any validation error, reporting the first offending
  message and field.
- **FR-003**: Check 2 (units) MUST FAIL if any `Detection.alt_m` falls outside the scenario's
  `[min_alt_m, max_alt_m]`, or any `Detection.accuracy_m` exceeds the sensor's `max_accuracy_m`.
- **FR-004**: Check 3 (coordinate frame) MUST FAIL if any `Detection` lies more than
  `range_m + 6 × accuracy_m` meters from the sensor's position (its configured `lat`/`lon`, or the
  defended-area center when omitted). The reason names the offending `detection_id`, its distance,
  and the limit. This replaces §4's "defended-area bounding box" wording, which would reject the
  known-good adapters' detections of the drone 3000 m from center when `radius_m` is 2000 m
  (Clarifications, Q4); architecture.md §4 is updated in the same PR.
- **FR-005**: Check 4 (timestamp/clock offset) MUST compute reference times from the harness's
  own inputs (`scenario.start_utc + raw.t_s` for each raw input it supplied), sort them, sort the
  adapter's `Detection.timestamp_utc` values, and FAIL if the counts differ or if any pairwise
  difference exceeds the scenario's configured `max_clock_offset_s` in either direction (ahead =
  "in the future", behind = "stale"). The reason states the largest measured offset, its
  direction, and the limit. It MUST NOT read `raw_payload` or any other adapter-supplied field as
  the reference (Clarifications, Q2). `Heartbeat` timing is covered by check 6, not check 4.
- **FR-006**: Check 5 (update rate) MUST measure the `Detection`-only rate on the full (no-gap)
  probe stream and FAIL if it falls outside the sensor's configured `[min_hz, max_hz]`. It MUST NOT
  count `Heartbeat`s toward cadence (ruled out in §13 as unfalsifiable).
- **FR-007**: Check 6 (heartbeat/liveness) MUST, on full probe-stream output sorted by
  `timestamp_utc`, FAIL if (a) any gap between consecutive messages (`Detection` or `Heartbeat`)
  exceeds the sensor's `heartbeat_timeout_s`, or (b) the stream's span (last minus first message
  time) falls short of the scheduled span (last minus first scheduled tick) by more than
  `heartbeat_timeout_s` — i.e. the adapter went silent early or started late.
- **FR-008**: The harness MUST feed each adapter two kinds of input: (a) the real scenario raw
  stream for that sensor, supplied by the caller; and (b) deterministic, harness-generated probe
  streams — one `RawDetection` per scheduled tick at a fixed position inside the sensor's coverage
  and plausible-units bounds, plus gap variants with selected ticks withheld. Checks 1–4 evaluate
  the adapter's output over all inputs; checks 5–7 evaluate only probe-stream output (Clarifications,
  Q3). Probe streams use no randomness, so results are identical across runs (Principle V).
- **FR-009**: Check 7 (dropped-message behavior) MUST inject synthetic gaps by withholding the
  probe stream's raw input for selected scheduled ticks, invoke the adapter, and FAIL if the adapter
  raises, if the number of `Detection`s differs from the number of raw inputs supplied (fabricated or
  lost detections), if the number of `Heartbeat`s differs from the number of withheld ticks (a gapped
  tick left unaccounted for, or a spurious `Heartbeat`), or if any `detection_id` is duplicated. It
  evaluates the adapter only; the fusion engine's coasting behavior under gaps is verified in #9, not
  here (Clarifications, Q1). architecture.md §4 check 7 is reworded accordingly in the same PR.
- **FR-009a**: Checks 5, 6, and 7 MUST be invariant to a constant `timestamp_utc` offset: they use
  counts, intervals between messages, and spans — never absolute times compared to the schedule.
  Clock alignment is exclusively check 4's responsibility, so an offset-only fault (the check-4
  fixture, and #8's sensor 3) fails check 4 alone (SC-002).
- **FR-010**: An aggregator MUST run all 7 checks against one adapter + sensor config + scenario
  and return a result set with an overall verdict: admitted only if all 7 PASS.
- **FR-011**: The gate MUST release an adapter's `Detection`s to downstream consumers only when
  its verdict is admitted; a blocked adapter's `Detection`s MUST be unreachable through the gate.
  `Heartbeat`s MUST never be released downstream (§3.4/§5).
  Because the fusion engine (#9) does not exist yet, the gate's "never reaches fusion" property is
  verified with a stub downstream consumer standing in for fusion.
- **FR-012**: A failing or exception-raising check MUST NOT prevent the other checks from running
  and reporting.
- **FR-013**: The harness MUST generate a Markdown report listing, per adapter, all 7 checks with
  PASS/FAIL and a one-line reason, plus the overall verdict. Output MUST be deterministic for
  identical inputs.
- **FR-014**: The harness MUST complete against both known-good adapters in under 60 seconds.
- **FR-015**: Conformance limits MUST be configured in YAML via `src/config/models.py`, extending —
  not redefining — the existing models, as required fields with no silent defaults (Clarifications,
  Q5):
  - `SensorConfig` (sensor properties): `min_hz`, `max_hz`, `max_accuracy_m`; validators reject
    `min_hz > update_rate_hz`, `update_rate_hz > max_hz`, and `accuracy_m > max_accuracy_m`.
  - `ScenarioConfig` (system acceptance limits a sensor cannot loosen for itself):
    `max_clock_offset_s`, `min_alt_m`, `max_alt_m`; validator rejects `min_alt_m >= max_alt_m`.
  `update_rate_hz` remains the nominal rate the adapter schedules on; `[min_hz, max_hz]` is the band
  check 5 accepts. This resolves §13 bullet (a).
- **FR-016**: The harness MUST NOT import simulator ground truth (`src.simulator.trajectories`,
  `src.simulator.scenario`), directly or indirectly, enforced by the `no-ground-truth-leak` import
  contract. That contract MUST also cover `src.adapters` again (re-added in this PR), and
  `detections.py`'s annotation-only `TruthObject` import MUST be `TYPE_CHECKING`-guarded with
  `exclude_type_checking_imports = True` so the contract evaluates runtime imports only.

### Key Entities

- **CheckResult**: one check's outcome — check number/name, passed (bool), one-line reason.
- **HarnessResult**: per-adapter aggregate — sensor id, the 7 `CheckResult`s, overall verdict
  (admitted/blocked).
- **Gate**: holds `HarnessResult`s and is the only path by which an adapter's `Detection`s reach
  downstream consumers.
- **Conformance limits**: sensor-property limits on `SensorConfig` (`min_hz`, `max_hz`,
  `max_accuracy_m`) and system acceptance limits on `ScenarioConfig` (`max_clock_offset_s`,
  `min_alt_m`, `max_alt_m`). Check 3's bound derives from existing `range_m`, `accuracy_m`, and
  sensor position.
- **Conformance report**: Markdown rendering of one or more `HarnessResult`s.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Both known-good adapters (sensors 1 & 2) PASS all 7 checks and are admitted.
- **SC-002**: A clock-offset-broken adapter fixture FAILS check 4 and PASSES the other 6 (0 false
  failures), and is blocked.
- **SC-003**: Each of the 7 check functions has at least one passing and one failing fixture,
  exercised against that check function directly, so a failing fixture demonstrates exactly the
  named fault. (Whole-harness isolation — only the target check fails — is required for the
  clock-offset fault, SC-002; it is not achievable in general, e.g. any rate fault that keeps the
  detection count must also shift timestamps.)
- **SC-004**: Zero `Detection`s from a blocked adapter are obtainable through the gate, verified by
  a test.
- **SC-005**: Full harness run against both known-good adapters completes in under 60 seconds.
- **SC-006**: Every check result in the report has exactly one non-empty reason line.

## Assumptions

- The harness lives in `src/conformance/` (§2) and consumes adapters only through the
  `SensorAdapter` protocol from #6 — never a concrete adapter's internals.
- The harness is invoked in-process (§3.3); it calls the adapter itself with
  `(raw_detections, sensor, scenario)`, so it knows exactly what input each adapter received.
- The real scenario raw stream is produced by the caller (the orchestrator in #13, or tests via
  `src.simulator.scenario`) and passed in; the harness never imports `src.simulator.scenario` or
  `src.simulator.trajectories`. The harness imports `RawDetection`/`expected_ticks` from
  `src.simulator.detections` and the `SensorAdapter` protocol from `src.adapters.base`; this is
  contract-clean only after the type-only import fix in Clarifications (planning-time decision).
- Report format is Markdown only (§4 says "Markdown/HTML"; Markdown is sufficient for the demo and
  the test record). HTML is out of scope.
- New limit fields are required (no silent defaults), following the precedent #6 set for
  `heartbeat_timeout_s`; `config/sensors/*.yaml`, `config/scenarios/example_scenario.yaml`, and
  existing test fixtures are updated.
- Real sensor-failure detection beyond "the adapter's output stream has a gap" is not required;
  check 6 evaluates the adapter's emitted stream, which is what the harness gates.
- Wiring the gate into the live tick loop is #13's job; #7 provides the gate API and proves it
  blocks with a test.
- The deliberately broken sensor-3 adapter itself is #8; #7 uses a local test fixture only.
