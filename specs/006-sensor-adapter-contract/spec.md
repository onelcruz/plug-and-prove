# Feature Specification: Sensor adapter contract (Detection schema + 2 known-good adapters)

**Feature Branch**: `006-sensor-adapter-contract`

**Created**: 2026-10-30

**Status**: Draft

**Input**: GitHub issue [#6](https://github.com/onelcruz/plug-and-prove/issues/6), architecture.md §3 (The sensor adapter contract)

## Why this is unsettled (not a settled issue)

Per constitution Principle VII, rule 1: this issue's heartbeat/liveness deliverable requires
resolving the open question in architecture.md §13 — "whether heartbeat is a distinct message
type or inferred from detection cadence for sensors with no target in view." Everything else in
this issue (the `Detection` schema, the coordinate-frame handling, in-process transport) is
already fully pinned down in architecture.md §3.1-§3.3 and is treated as settled/locked here; only
the heartbeat design is a genuine open decision this spec exists to resolve.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Sensor 1 and sensor 2 feed valid detections into the pipeline (Priority: P1)

As the orchestrator, I need sensor 1 and sensor 2's raw simulator output translated into the
canonical `Detection` message, so that later pipeline stages (conformance harness, fusion) can
consume a single, uniform schema regardless of which sensor produced a detection.

**Why this priority**: Without this, no sensor can feed the rest of the pipeline at all — this is
the foundational contract the entire epic's "plug in a new sensor" claim depends on.

**Independent Test**: Run each adapter against a `RawDetection` stream produced by
`src/simulator/detections.py` (issue #5) for that sensor, and confirm every resulting object is a
valid `Detection` per architecture.md §3.1's field table.

**Acceptance Scenarios**:

1. **Given** a `RawDetection` from sensor 1 (or sensor 2) with sim-clock `t_s` and a lat/lon/alt
   position, **When** the corresponding adapter translates it, **Then** the output is a `Detection`
   object with every required field populated, correct units (`alt_m` in meters AGL, `accuracy_m`
   in meters 1-sigma), and `timestamp_utc` correctly derived from `t_s` plus the scenario's start
   time (no clock-offset bug — that is scoped to the separate, deliberately-broken third adapter
   in #8).
2. **Given** a `RawDetection` with no velocity or confidence information (sensors 1/2's raw output
   per #5 does not currently produce these), **When** translated, **Then** `velocity_mps` and
   `confidence` are `None` (both are optional per the schema) rather than fabricated.

### User Story 2 - A new sensor can be added without touching contract/simulator code (Priority: P1)

As a developer adding a third sensor later, I need to implement only the `SensorAdapter`
interface plus a config entry, so that the adapter contract's extensibility promise (the epic's
core SBIR claim) is real, not aspirational.

**Why this priority**: This is explicitly called out as the property "the whole epic depends on"
in the issue's acceptance criteria — it must be verified directly, not assumed from the two
adapters alone looking similar.

**Independent Test**: Write a throwaway third test adapter implementing `SensorAdapter` with no
changes to `src/simulator/`, the `Detection` schema, or any other adapter's code, and confirm it
produces valid `Detection` objects.

**Acceptance Scenarios**:

1. **Given** a new, minimal test adapter implementing only the `SensorAdapter` interface, **When**
   it is registered and run, **Then** it produces valid `Detection` objects without any change to
   `src/simulator/`, `src/config/models.py`'s existing fields, or sensor 1/2's adapters.

### User Story 3 - A sensor's schedule-coverage is observable (Priority: P2)

As the conformance harness (next issue, #7) and fusion engine (later, #9), I need to know, for
every scheduled tick, whether a sensor reported a `Detection` or an explicit `Heartbeat` — so a
tick with no target in view is distinguishable, in the output stream, from a tick that was simply
never produced at all.

**Why this priority**: Required for this issue's heartbeat deliverable, but downstream (harness
check 6, fusion's track-coasting behavior) rather than blocking for #6 itself — hence P2, not P1.

**Scope note (added after rubber-duck review #2)**: this story is about *schedule-coverage
bookkeeping* — "did the adapter account for this tick" — not real sensor-failure detection.
`translate()` recomputes the expected schedule from config and cannot observe whether the
upstream feed was actually still being produced; see `plan.md`'s "Known limitation" for why
genuine liveness/failure detection is explicitly deferred to #7.

**Independent Test**: Run an adapter across a stretch of sim-ticks where its truth object is out
of range/non-existent, and confirm a `Heartbeat` is produced at the sensor's configured
update-rate cadence for each such tick, without a `Detection` being fabricated for a non-existent
target.

**Acceptance Scenarios**:

1. **Given** a sensor configured with `update_rate_hz` and a new `heartbeat_timeout_s` field, and
   a tick where no truth object is in range, **When** the adapter runs that tick, **Then** it
   emits a `Heartbeat` for that tick instead of a `Detection`.
2. **Given** the full set of scheduled ticks for a sensor's `update_rate_hz` and
   `scenario.duration_s`, **When** `translate()` runs, **Then** every tick produces either a
   `Detection` or a `Heartbeat` — there are no unaccounted-for ticks in the output. (Note: this
   does **not** cover a sensor that is actually dead/non-reporting — see scope note above;
   `translate()` has no way to receive evidence of that from today's inputs.)

### Edge Cases

- What happens when a sensor has zero truth objects in range for its entire configured
  `heartbeat_timeout_s` window — does the adapter still emit *something*, and if so, what?
  (Yes: a `Heartbeat` per scheduled tick.)
- How does the heartbeat mechanism interact with `dropout_probability` (§2, existing `SensorConfig`
  field) — is a dropped detection indistinguishable from "no target"? (Yes, intentionally — both
  produce a `Heartbeat`; see `plan.md` disposition item 5.)
- What happens at the very first tick (t_s = 0)? (Handled identically to every other scheduled
  tick — no special-case startup semantics, since both sides compute the same schedule.)
- What is emitted for a sensor with `update_rate_hz` configured but whose adapter is never polled
  at exactly that cadence? (Not applicable to this design: `translate()` is a pure batch function
  over the full `RawDetection` list, there is no live per-tick polling of the adapter itself.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST define a `Detection` pydantic model matching architecture.md
  §3.1's field table exactly: `sensor_id` (str), `detection_id` (str), `timestamp_utc` (float,
  seconds since Unix epoch UTC), `lat`/`lon` (float, decimal degrees WGS84), `alt_m` (float,
  meters AGL), `accuracy_m` (positive float, meters 1-sigma), `velocity_mps` (optional float,
  m/s), `confidence` (optional float, 0.0-1.0), `raw_payload` (dict).
- **FR-002**: The system MUST define a `SensorAdapter` interface/protocol that every adapter
  (present and future) implements, such that the harness, fusion engine, and orchestrator interact
  with any adapter only through this interface — never through a concrete adapter's internals.
- **FR-003**: The system MUST provide a concrete adapter for sensor 1 that translates
  `RawDetection` objects (from `src/simulator/detections.py`, issue #5) into valid `Detection`
  objects, converting `t_s` (sim-clock seconds) to `timestamp_utc` (UTC epoch) using the
  scenario's configured start time, with no injected clock-offset error.
- **FR-004**: The system MUST provide a second, equivalent concrete adapter for sensor 2.
- **FR-005**: A new sensor adapter MUST be addable by implementing `SensorAdapter` plus a
  `SensorConfig` entry, with zero required changes to `src/simulator/`, the `Detection` schema, or
  any other adapter — verified by an explicit throwaway test adapter (User Story 2).
- **FR-006**: The system MUST provide an explicit `Heartbeat` message (resolved via `plan.md`'s
  rubber-duck-reviewed design: a pure, stateless, batch-computed signal, not inferred adapter
  instance state) so a consumer (harness, fusion engine) can determine that a scheduled tick was
  accounted for — either a `Detection` or a `Heartbeat` — even when no target was in view and no
  `Detection` was produced. **Scope note**: this proves schedule-coverage, not real sensor
  liveness/failure — see `plan.md`'s "Known limitation"; genuine dead-sensor detection is
  explicitly deferred to #7.
- **FR-007**: `SensorConfig` MUST gain `heartbeat_timeout_s`, extending the existing model in
  `src/config/models.py` rather than redefining it, consistent with that file's existing module
  docstring guidance, and MUST validate `heartbeat_timeout_s >= 1 / update_rate_hz` at construction
  time (rejecting configs that could never satisfy architecture.md §3.4's timing requirement by
  construction — added after rubber-duck review #3 found the field was otherwise unenforced).
- **FR-008**: `ScenarioConfig` MUST gain a `start_utc` field (a configured, deterministic Unix
  epoch value), so `timestamp_utc = start_utc + t_s` is identical across repeated runs with the
  same seed and configuration — required by constitution Principle V (reproducibility); using
  real wall-clock time at run start would violate it.
- **FR-009**: `Detection.detection_id` MUST be deterministically generated (not supplied by the
  raw sensor output, which has no such field) as `f"{sensor_id}:{tick_index}:{index_within_tick}"`,
  unique even when multiple targets are detected by the same sensor at the same tick, and immune
  to floating-point timestamp-precision collisions at high update rates (hence the integer tick
  index rather than a formatted `t_s` float). **Assumption** (recorded per rubber-duck review #3,
  not enforced by this issue): this is globally unique only if `sensor_id` is unique across all
  configured sensors in a scenario; enforcing that, if needed, is a config-loading/orchestration
  concern, not an adapter concern.
- **FR-010**: `translate()` MUST raise on any input `RawDetection.t_s` that doesn't exactly match
  a value produced by `expected_ticks(sensor.update_rate_hz, scenario.duration_s)` — an
  off-schedule input is a contract violation, not something to silently drop or misattribute.
- **FR-011**: `translate()` MUST raise on any input `RawDetection` whose `sensor_id` doesn't match
  the `sensor.sensor_id` the adapter is invoked with — a misrouted/mixed-sensor batch is a
  contract violation, same treatment as FR-010's off-schedule case. `Detection.sensor_id` MUST
  always come from the configured `sensor.sensor_id`, never copied from raw input, so there is one
  unambiguous source of sensor identity (added after independent review).
- **FR-012**: `list[Detection | Heartbeat]` output feeds the conformance harness (architecture.md
  §4) in full; only the `Detection` entries are forwarded to the fusion engine, consistent with
  architecture.md §5's locked "canonical `Detection` objects (post-harness-gate)" input contract.
  `Heartbeat` entries are not fusion input (added after independent review flagged this boundary
  as previously implicit).

### Key Entities

- **Detection**: The canonical, schema-validated message every adapter emits — the extensibility
  seam the whole epic's "plug in a new sensor" claim rests on. Defined in architecture.md §3.1.
- **Heartbeat**: A new, explicit pydantic message (`sensor_id`, `t_s`) emitted by `translate()` for
  any scheduled tick with no corresponding `Detection` — satisfies architecture.md §3.4's existing
  "emit... an explicit heartbeat/liveness signal" wording directly.
- **SensorAdapter**: The interface/protocol contract — a single pure function,
  `translate(raw_detections, sensor, scenario) -> list[Detection | Heartbeat]`. Not a data entity,
  but the structural boundary that must remain stable as new sensors are added.
- **RawDetection**: The existing, pre-adapter, sensor-specific message (from #5) that each
  concrete adapter consumes as input. Already implemented; not modified by this issue except as a
  read-only input.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of `Detection` objects produced by either adapter, across a full scenario run,
  pass pydantic validation against the exact field table in architecture.md §3.1.
- **SC-002**: A throwaway third adapter can be implemented and produce valid detections with zero
  lines changed in `src/simulator/`, `src/adapters/` (other than adding the new file itself), or
  `Detection`'s definition — demonstrated by an actual test, not asserted.
- **SC-003**: For any tick where a sensor has no target in range, a consumer can determine that
  the tick was accounted for (schedule-coverage, not real liveness — see FR-006's scope note),
  without a `Detection` ever being fabricated for a non-existent target.
- **SC-004**: Unit tests cover schema conformance, unit correctness, and the heartbeat/
  schedule-coverage behavior for both concrete adapters and the extensibility test adapter.

## Assumptions

- Sensor 1 and sensor 2's existing `SensorConfig` entries in `config/sensors/example_sensor.yaml`
  (from #5) are reused as-is, extended with `heartbeat_timeout_s` (a per-sensor field); separately,
  `config/scenarios/example_scenario.yaml`'s scenario-level config gains `start_utc`. (Corrected
  after rubber-duck review #2 flagged that an earlier draft of this spec/plan wrongly assumed both
  new fields belonged on the scenario file — verified against the actual repo layout.)
- The scenario's "start time" (for converting `t_s` to `timestamp_utc`) is a configured,
  deterministic `start_utc` field on `ScenarioConfig`, not wall-clock time at simulation start —
  revised after rubber-duck review identified that wall-clock "now" would violate constitution
  Principle V's reproducibility requirement (identical seed/config must produce identical
  detections, including their `timestamp_utc`, across runs).
- In-process, synchronous translation (§3.3, locked) — no async/threading concerns for heartbeat
  timing; heartbeat ticks are computed from simulated time (`t_s`) via the same shared
  `expected_ticks()` helper `generate_sensor_detections` already uses, not real wall-clock time.
- Real sensor-failure detection (distinguishing a dead sensor from a healthy idle one) is
  explicitly **out of scope** for this issue — `translate()` has no evidence of actual feed
  coverage beyond the nominal schedule computed from config. See `plan.md`'s "Known limitation."
- The deliberately-broken third adapter (clock-offset bug) is out of scope for this issue per its
  explicit "Out of scope" section — it is filed separately as #8 and will extend, not replace, the
  `SensorAdapter` interface defined here.
- Architecture.md §3.4's `[min_hz, max_hz]` update-rate range is not implemented here —
  `SensorConfig` still only has a single `update_rate_hz` (a pre-existing gap from #5). This is
  explicitly deferred to #7 (the conformance harness, which owns the rate check), not fixed
  retroactively in this issue.
