# Implementation Plan: Sensor adapter contract (Detection schema + 2 known-good adapters)

**Branch**: `006-sensor-adapter-contract` | **Date**: 2026-10-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/006-sensor-adapter-contract/spec.md`

## Summary

Define the canonical `Detection` pydantic model and `SensorAdapter` protocol (architecture.md
§3.1-§3.3), implement two concrete adapters translating sensor 1 and sensor 2's existing
`RawDetection` output (from #5, `src/simulator/detections.py`) into `Detection` objects, and
resolve the open heartbeat/liveness design question (§13) by extending `SensorConfig` with a
`heartbeat_timeout_s` field and emitting an explicit `Heartbeat` message (not inferred adapter
instance state) for any scheduled tick with no matching `RawDetection` — see "Heartbeat design
decision" below for the full reasoning, rejected alternatives, and the honestly-scoped limitation
this issue does *not* solve (detecting a genuinely silent/failed sensor, deferred to #7).

## Technical Context

**Language/Version**: Python 3.11+ (matches existing codebase)

**Primary Dependencies**: `pydantic` (schema validation, matches `src/config/models.py` and
`src/simulator/detections.py`), `numpy`'s RNG only indirectly (adapters are deterministic
translations of already-generated `RawDetection`s — no new randomness introduced here)

**Storage**: N/A — in-process objects only, per architecture.md §3.3 (locked)

**Testing**: `pytest`, matching `tests/test_trajectories.py` / `tests/test_detections.py` style

**Target Platform**: Single local machine, offline (constitution Principle II)

**Project Type**: Single Python project (existing `src/` layout)

**Performance Goals**: N/A — no stated latency/throughput target; must simply complete well
within the harness's existing 60-second budget (architecture.md §4) once chained with later
issues

**Constraints**: Must not modify `src/simulator/`, the `Detection` schema (once defined here), or
any other adapter when a new adapter is added later (architecture.md §3, "no changes to the
harness, fusion engine, classifier, or output layer")

**Scale/Scope**: Two concrete adapters (sensor 1, sensor 2) + the `SensorAdapter`
interface/protocol + the `Detection` schema + one throwaway test adapter used only to prove
extensibility (not shipped as permanent production code)

## Constitution Check

*GATE: Must pass before implementation.*

- **Principle I (Architecture-First)**: Implements architecture.md §3 directly; the one
  deviation (resolving §13's heartbeat question) is written back into architecture.md in the same
  PR, per Principle I's requirement. ✅ (planned, not yet done — see "Architecture doc update"
  below)
- **Principle III (Test-First & CI-Gated)**: `Detection`/`SensorAdapter` introduce no novel
  numerical/statistical logic (pure translation + validation), but the heartbeat/liveness
  mechanism *is* non-trivial logic (a timing/threshold decision) — independent review is
  mandatory for that part before merge. ✅ planned.
- **Principle IV (Narrow, Contract-Bound Changes)**: Stays inside `src/adapters/` (new) and
  `src/config/models.py` (extend, don't redefine), with one deliberate, minimal exception: the
  `expected_ticks()` extraction into `src/simulator/detections.py` (behavior-preserving, see
  disposition item 15). No other changes to `src/simulator/`, `src/conformance/`, `src/fusion/`,
  or later-stage modules. ✅
- **Principle V (Reproducibility)**: Adapters are pure deterministic functions of
  already-generated `RawDetection` objects — no new RNG usage. `start_utc` and the new
  `detection_id` scheme are new deterministic outputs this issue introduces, so (corrected after
  independent review — see disposition item 28) they are **not** automatically covered by #5's
  existing tests; the planned `timestamp_utc`/`detection_id` determinism tests in
  `tests/test_adapters.py` are required reproducibility evidence for this issue, not optional. ✅
  (planned, not yet done)
- **Principle VI (Explainability)**: N/A directly — `Detection` doesn't carry a "reason" field in
  architecture.md's schema (that's introduced at the classifier/recommendation stages). No
  violation; just not applicable at this layer.
- **Principle VII (settled vs. unsettled)**: This issue is unsettled per rule 1 (heartbeat, §13).
  This plan, and the rubber-duck review of it, exist specifically to satisfy that requirement
  before implementation starts.

No constitution violations requiring a Complexity Tracking justification.

## Heartbeat design decision (resolves architecture.md §13)

**Question**: "Whether heartbeat is a distinct message type or inferred from detection cadence
for sensors with no target in view."

**Decision (revised after rubber-duck review — see "Rubber-duck review disposition" below)**: a
distinct, explicit `Heartbeat` pydantic message, computed by `translate()` as a pure, stateless,
batch operation — not inferred from adapter instance state and not requiring any new
orchestrator-driven per-tick invocation API.

Concretely:
- `SensorConfig` gains `heartbeat_timeout_s: PositiveFloat`, with a model validator enforcing
  `heartbeat_timeout_s >= 1 / update_rate_hz` (a tick's worth of slack, at minimum). Without this,
  the field would be decorative: a consumer could configure, say, `update_rate_hz=0.1` (one
  scheduled tick every 10s) with `heartbeat_timeout_s=1`, and architecture.md §3.4's "within
  `heartbeat_timeout_s`" requirement would be violated by construction on *every* idle tick, by a
  design that can never emit faster than the schedule allows. Rejecting that combination at config
  load time (rather than silently allowing a harness check to fail later) is the one explicit
  invariant this plan commits to, per rubber-duck review #3's finding.
- A shared, pure helper — `expected_ticks(update_rate_hz, duration_s) -> list[float]` — is
  extracted into `src/simulator/detections.py` (a small, behavior-preserving refactor:
  `generate_sensor_detections` is updated to call it instead of inlining the formula) and
  re-exported for `translate()` to import. This removes the duplicated-formula risk flagged by
  the second rubber-duck review (disposition item 13 below): there is now exactly one place that
  defines "what a sensor's scheduled ticks are," so the adapter and the simulator are
  structurally incapable of silently drifting apart. `translate()` requires every input
  `RawDetection.t_s` to equal one of `expected_ticks()`'s values exactly (both sides call the same
  helper, so this holds for any input actually produced by `generate_sensor_detections`); a
  `RawDetection` whose `t_s` doesn't match any scheduled tick is a contract violation and
  `translate()` raises rather than silently dropping or misattributing it.
- For each scheduled tick (iterated via `enumerate(expected_ticks(...))`, so `tick_index` is that
  enumeration index): if one or more `RawDetection`s exist at that `t_s` — grouped in the stable
  order they appear in the input `raw_detections` list — emit a `Detection` per raw detection; if
  none exist (whether because no target was in range, no target existed, *or*
  `dropout_probability` dropped it), emit exactly one `Heartbeat(sensor_id, t_s)` instead.
  **Precise, input-observable semantics (tightened after rubber-duck review #3 — avoid overclaiming
  what's actually knowable)**: a `Heartbeat` means only "`translate()` received no `RawDetection`
  for this nominal scheduled tick." It does **not** establish *why* (no target, out of range, or
  dropout are all indistinguishable, which is fine — disposition item 5), and critically it does
  **not** establish that the upstream sensor/feed was actually alive at that tick — see "Known
  limitation" immediately below for why, and why that's an explicit, accepted boundary of #6.
- **Consumer boundary (made explicit after independent review — see disposition item 23)**: the
  harness reads the full `list[Detection | Heartbeat]` for its checks (schema/units/coordinate
  checks apply to `Detection` entries only; the heartbeat/liveness check in architecture.md §4
  reads both types). **Fusion does not** — architecture.md §5 already locks fusion's input as
  "canonical `Detection` objects (post-harness-gate)" only. The orchestrator (full wiring lands in
  #13, not this issue) is responsible for filtering `list[Detection | Heartbeat]` down to
  `Detection`-only before the fusion handoff; `Heartbeat` entries are consumed solely by the
  harness's liveness bookkeeping (and, later, by architecture.md §4 check 7's gap-injection/
  coasting test). #6's job is to make this boundary an unambiguous, testable part of the contract
  — e.g. a simple test asserting `isinstance` filtering of `translate()`'s own output correctly
  separates the two types — not to build the orchestrator's actual wiring, which stays #13's
  deliverable. This was previously left implicit; it's now stated so #7 and #13 don't have to
  guess it.

**Known limitation (new, honestly scoped — not silently resolved)**: because `translate()`
independently recomputes the *expected* schedule from `sensor.update_rate_hz` and
`scenario.duration_s` rather than reading any evidence of what was *actually* polled, it cannot
distinguish "sensor alive, nothing to report" from "sensor silently stopped reporting entirely."
Today this is harmless because `generate_sensor_detections` (#5) has no failure mode at all — it
always computes the full schedule deterministically, so there is no real "dead sensor" condition
anywhere upstream for `translate()` to fail to notice. But this means **`Heartbeat` as designed
here cannot yet serve as a true liveness check** — it will "fill in" a `Heartbeat` even across a
gap that a future harness fault-injection mechanism (architecture.md §4 check 7, "dropped-message
behavior") deliberately introduces, masking exactly the failure that check is meant to catch.
Resolving this requires the harness (#7) to supply `translate()` with actual evidence of how far
the raw feed was really produced (not just the scenario's nominal duration) — a mechanism that
does not exist yet and is explicitly **out of scope for #6**. This is recorded as a new
architecture.md §13 open question (see "Architecture doc update" below), not papered over: #6
delivers the `Detection`/`Heartbeat` schema and two conformant adapters per architecture.md
§3.1-§3.4; it does **not** deliver real sensor-failure detection, and User Story 3 / FR-006 below
are revised to state that boundary explicitly rather than imply a capability that doesn't exist.

**Why this is now consistent with architecture.md §3.4 (locked wording)**: §3.4 already states an
adapter "must emit a `Detection` (or an explicit heartbeat/liveness signal...) within
`heartbeat_timeout_s`." The revised design emits a literal, named `Heartbeat` signal — satisfying
that wording directly, rather than requiring an architectural amendment to §3.4 (as the
cadence/instance-state design from the first draft of this plan would have needed).

**Alternative considered and rejected (original plan draft, reversed after review)**: deriving
liveness purely from adapter instance state (`last_seen_at(t_s)`), with the orchestrator calling
every adapter every tick regardless of target presence. Rejected on reflection because: (a) no
such per-tick orchestrator invocation contract exists yet or is scoped to this issue — inventing
one here would be scope creep into #9/#13's territory; (b) adapter instance state isn't observable
by a harness that evaluates a completed output batch (architecture.md §4's natural execution
model) without also redefining how the harness is invoked; (c) it would have left §3.4's locked
wording ("emit... a signal") inconsistent with a design that emits nothing. The batch/pure-function
`Heartbeat` design above avoids all three problems while resolving the same §13 question.

### Rubber-duck review disposition

A `rubber-duck` review of this plan's first draft (proposing cadence/instance-state liveness) was
run before implementation began. It raised 12 points; this is the disposition of each:

1. **(Blocking, resolved)** First draft had no source of "empty ticks" from the batch-oriented
   simulator — resolved by having `translate()` independently recompute the identical tick
   schedule from public config fields (`update_rate_hz`, `duration_s`), requiring zero changes to
   `src/simulator/`.
2. **(Blocking, resolved)** Instance state wasn't observable by a batch-evaluating harness —
   resolved by making `Heartbeat` an explicit, emitted entry in the same returned list as
   `Detection`, fully observable from the completed output alone.
3. **(Blocking, resolved)** First draft conflicted with §3.4's locked "must emit... a signal"
   wording — resolved by actually emitting a named `Heartbeat` signal; no architecture.md §3.4
   amendment needed, only §13's pointer update.
4. **(Blocking, resolved)** Startup (`t_s=0`) and cadence-tolerance semantics were undefined with
   instance state — resolved: ticks are an exact, independently-computed formula on both sides, so
   there is no "first poll" ambiguity or floating-point tolerance question; `t_s=0` is tick `i=0`,
   handled identically to every other tick (`Detection` if a target was there, `Heartbeat` if not).
5. **(Non-blocking, resolved/accepted by design — wording tightened after review #3)**
   `dropout_probability` vs. "alive" — intentionally collapsed: a dropped detection, an
   out-of-range target, and no target at all are all represented as the same `Heartbeat` for that
   tick. **Precise framing**: a `Heartbeat` means "no `RawDetection` was present for this nominal
   scheduled tick" — nothing more. It does not assert the sensor was "functioning normally" (an
   earlier draft of this item overclaimed that); see the tightened semantics above and the "Known
   limitation" section. Test coverage: `heartbeat_timeout_s` is unaffected by *which* of the three
   caused a given tick's `Heartbeat` — tests assert the `Heartbeat` appears, not which cause
   triggered it, since the adapter has no way to distinguish them from `RawDetection` alone (by
   design, since #5's `RawDetection` doesn't carry a "why no detection" field).
6. **(Non-blocking, explicitly deferred)** Architecture.md §3.4 also describes a `[min_hz, max_hz]`
   update-rate range, but `SensorConfig` (from #5) only has a single `update_rate_hz` — a
   pre-existing mismatch from #5, not introduced here. Out of scope for #6 (the harness's rate
   check is #7's deliverable, not an adapter concern); flagged explicitly in the architecture.md
   pointer update (see below) as a gap for #7 to resolve, not silently left implicit.
7. **(Blocking, resolved)** `SensorAdapter`'s entry point is now fully specified: a single pure
   method, `translate(raw_detections: list[RawDetection], sensor: SensorConfig,
   scenario: ScenarioConfig) -> list[Detection | Heartbeat]`, stateless, requiring nothing beyond
   data already available to any caller (no registration lifecycle, no hidden state) — this is
   what makes the throwaway extensibility adapter (spec User Story 2 / SC-002) a meaningful proof,
   not just a protocol-conformance test.
8. **(Non-blocking, resolved — revised again after review #2, see item 14)** `detection_id` is
   now specified: deterministic and collision-safe as
   `f"{sensor.sensor_id}:{tick_index}:{index_within_tick}"`, where `tick_index` is the integer
   position in the shared `expected_ticks()` schedule (not a formatted float) and
   `index_within_tick` disambiguates multiple simultaneous `RawDetection`s at the same tick (e.g.
   two targets in range of one sensor at once), assigned in the stable input order of
   `raw_detections` for that tick (Python list iteration order, which is itself deterministic
   given #5's deterministic generation order — no new ordering rule invented). `raw_payload` is
   `raw.model_dump()` — the full `RawDetection`, matching §3.1's "original untranslated sensor
   output" definition exactly.
9. **(Blocking, resolved)** `timestamp_utc` ownership/reproducibility — the plan's first draft
   assumed wall-clock "now" at orchestrator start, which **violates constitution Principle V**
   (identical seed/config MUST produce identical detections across runs, and a wall-clock-derived
   `timestamp_utc` would differ run-to-run even with the same seed). Resolved: `ScenarioConfig`
   gains a new field, `start_utc: NonNegativeFloat` (seconds since Unix epoch), explicitly
   configured per-scenario rather than read from the real clock. `timestamp_utc = start_utc + t_s`
   for every adapter, and this same `scenario.start_utc` is the single shared reference the
   harness (#7) will use for its clock-offset check — same source, trivially handed off, fully
   reproducible.
10. **(Sound, kept)** `Detection` living in `src/adapters/` rather than `src/config/models.py` —
    confirmed correct: it's a pipeline message schema (like `RawDetection`), not YAML-loaded
    configuration.
11. **(Accuracy note, applied)** `src/adapters/` is an existing placeholder package (per
    architecture.md §2's suggested layout, with an existing empty `__init__.py`), not a new one —
    corrected in "Project Structure" below; this issue populates it, it doesn't introduce it.
12. **Noted**: the reviewer observed the rejected cadence/instance-state design could have been
    reasonable *if* a stronger, already-established live-tick execution contract existed. None
    does yet (that's #9/#13's territory), which is precisely why the batch/pure-function
    `Heartbeat` design — needing no such contract — was chosen instead.

A **second** `rubber-duck` review was run against this revised plan (per the "don't assume the fix
worked, re-review" standard in `.github/copilot-instructions.md`). It confirmed all 4 original
blocking points above are mechanically resolved, then raised 2 **new** blocking points and 3
non-blocking points:

13. **(Blocking, resolved)** Critical semantic flaw: synthesizing a `Heartbeat` for every tick
    with no `RawDetection` means a genuinely dead/non-reporting sensor is indistinguishable from a
    healthy one with no target in view — the design "manufactures liveness from configuration
    alone." This directly contradicted User Story 3's own stated edge case (a sensor that truly
    stops reporting should become observably "not alive"). **Resolved by scoping down, not by
    inventing a fake fix**: added the "Known limitation" callout above, revised User Story 3/FR-006
    in spec.md to claim only what `translate()` can honestly deliver (schedule-coverage
    bookkeeping, not real failure detection), and opened a new architecture.md §13 question for
    #7 to resolve. Also extracted the shared `expected_ticks()` helper (see above) so that when
    #7 does tackle this, there is exactly one schedule definition to extend with real evidence,
    not two to keep in sync.
14. **(Blocking, resolved)** The plan's Summary section (top of this file) still described the
    rejected cadence/instance-state design after the detailed sections below it had already been
    revised — an implementer reading only the Summary would have built the wrong thing. Fixed:
    Summary now matches the batch/`Heartbeat` design and references this section.
15. **(Non-blocking, resolved)** Fragile duplicated tick-schedule formula — resolved by extracting
    `expected_ticks()` into `src/simulator/detections.py` and having both `generate_sensor_detections`
    and `translate()` call it (see above); this is a deliberate, minimal, behavior-preserving touch
    to `src/simulator/` despite #6's module boundary nominally being `src/adapters/` — justified
    because the alternative (duplicated logic across two modules) is exactly the kind of drift
    Principle VII's architecture-health pass exists to catch, and it's cheaper to prevent now than
    to detect later. Will be called out explicitly in the implementing PR's description.
16. **(Non-blocking, resolved)** `detection_id` collision/ordering — resolved by disposition item
    8 above (tick index instead of formatted float, stable input-order tie-break).
17. **(Non-blocking, resolved)** Incomplete change inventory — the plan did not list the existing
    config YAML files or existing test fixtures that will break once `heartbeat_timeout_s` and
    `start_utc` become fields on `SensorConfig`/`ScenarioConfig`. Resolved: "Project Structure"
    below now enumerates every file to update, including a verification step for the actual config
    YAML location (the plan had assumed `config/scenarios/example_scenario.yaml` without checking).

A **third** `rubber-duck` review was run against this revised plan/spec. It confirmed the 5 items
above are genuinely, mechanically resolved (not just asserted), then raised 2 new blocking points
and 3 non-blocking points:

18. **(Blocking, resolved)** `heartbeat_timeout_s` had no enforced semantics — a config combining
    a slow `update_rate_hz` with a short `heartbeat_timeout_s` (e.g. one tick every 10s with a
    1s timeout) would violate architecture.md §3.4's "within `heartbeat_timeout_s`" requirement by
    construction, on every idle tick, with no way for the adapter to emit faster than its own
    schedule allows. Resolved: `SensorConfig` gains a model validator requiring
    `heartbeat_timeout_s >= 1 / update_rate_hz`, rejected at config-load time rather than
    discovered later as a harness check failure.
19. **(Blocking, resolved)** Residual overclaiming: the design and disposition item 5 described a
    `Heartbeat` as meaning the sensor was "alive" / "functioning normally," which is exactly the
    claim the "Known limitation" says can't be made. Resolved: reworded to strictly
    input-observable language throughout ("no `RawDetection` was present for this nominal
    scheduled tick," nothing about the upstream sensor's real state) — see the tightened Heartbeat
    design decision above and disposition item 5's revision.
20. **(Non-blocking, resolved)** The `RawDetection`-to-schedule matching rule wasn't fully
    specified — resolved: `translate()` requires every input `RawDetection.t_s` to exactly match
    one of `expected_ticks()`'s values (guaranteed when the input actually comes from
    `generate_sensor_detections`, since both call the same helper) and **raises** on any
    off-schedule `t_s` rather than silently dropping it; grouping is by `enumerate(expected_ticks())`
    with raw detections matched in their original list order.
21. **(Non-blocking, accepted as a recorded assumption)** `detection_id` uniqueness depends on
    `sensor_id` being unique across all configured sensors in a scenario — not currently enforced
    by `SensorConfig`/config loading. Recorded explicitly here as a contract assumption this issue
    relies on but does not enforce; enforcing global `sensor_id` uniqueness at config-load time, if
    needed, belongs to the orchestration/config-loading issue, not #6.
22. **(Non-blocking, resolved)** Test coverage for `expected_ticks()` itself (not just its callers)
    is now an explicit task: assert `t_s=0` inclusion, a non-binary-exact rate (e.g. 7 Hz), a
    duration/rate combination where the final tick isn't exactly `duration_s`, and exact equality
    between `generate_sensor_detections`'s produced `t_s` values and `expected_ticks()`'s output —
    added to `tests/test_adapters.py`'s scope in "Project Structure" below.

A **fourth** review was commissioned as a genuinely **independent, cold** review (fresh context,
no prior involvement in this plan's history) specifically because 3 self-initiated re-reviews of
one's own fix risks converging on confirmation rather than catching new classes of problem. It
found 2 new blocking issues, 3 non-blocking issues, and one claim this plan disputes with direct
evidence (recorded as item 26):

23. **(Blocking, resolved)** The plan never stated who consumes `Heartbeat` entries downstream.
    Architecture.md §5 already locks fusion's input as "canonical `Detection` objects
    (post-harness-gate)" — `Heartbeat` was never meant to reach fusion, but the plan's own text
    said "a consumer (harness, fusion) reads... `list[Detection | Heartbeat]`," implying fusion
    might see heartbeats too, which would silently violate the already-locked §5 contract.
    Resolved: added an explicit "Consumer boundary" statement (see Heartbeat design decision
    above) — the orchestrator filters to `Detection`-only before the fusion handoff; `Heartbeat`
    is consumed by the harness (and later, #7's gap-injection/coasting check) only.
24. **(Blocking, resolved — flagged forward to #7, not fixed here)** Architecture.md §4 check 5
    ("measured inter-detection interval... falls within `[min_hz, max_hz]`") is now ambiguous
    given this design: during a stretch where a sensor's truth object is out of view, the output
    is all `Heartbeat`, zero `Detection`, so an "inter-detection interval" literally cannot be
    measured — not a bug in #6, but existing locked wording that no longer cleanly describes the
    harness's job once #6 introduces `Heartbeat`. This is a **harness-implementation** question
    (#7 owns check 5), not something #6 can resolve by itself, so it's recorded as a new
    architecture.md §13 open question (see "Architecture doc update" below) rather than
    silently left for #7 to discover independently.
25. **(Non-blocking, resolved)** No validation that an input `RawDetection.sensor_id` matches the
    `SensorConfig.sensor_id` the adapter was invoked with. Resolved: `translate()` now also raises
    if any `raw_detections` entry's `sensor_id` doesn't match `sensor.sensor_id` — a misrouted
    mixed-sensor batch is a contract violation, same treatment as an off-schedule `t_s` (item 20).
    `Detection.sensor_id` is always the configured `sensor.sensor_id`, never copied from the raw
    input, so there's one unambiguous source of truth for sensor identity.
26. **(Reviewed and rejected, with evidence)** The reviewer argued the extensibility claim (spec
    User Story 2 / SC-002) is narrower than architecture.md's "plug in a new sensor" promise,
    because the protocol is fixed to `RawDetection` as input. **Checked against the actual locked
    text**: architecture.md line 80 states the promise precisely as "adding a new sensor means
    writing one adapter module + one config entry — **no changes to the harness, fusion engine,
    classifier, or output layer**" — it does not claim "no changes to the simulator." Generating
    a new sensor's raw output is already, by design, the simulator's job (§2), separate from the
    adapter's job of translating that raw output into `Detection`. #6's extensibility proof (a
    throwaway adapter over the existing `RawDetection` type) matches exactly what's actually
    promised; no change made.
27. **(Non-blocking, accepted as a recorded assumption)** Exact float equality between an input
    `RawDetection.t_s` and `expected_ticks()`'s output is only guaranteed when both are computed by
    the same in-memory call path — true today because architecture.md §3.3 (locked) specifies
    in-process, non-serialized transport for this demo. Recorded explicitly: if a future adapter
    ever receives `RawDetection` reconstructed from serialized data (JSON/YAML round-trip), float
    equality could spuriously fail even for on-schedule input. Out of scope for #6 given §3.3's
    current lock; flagged here rather than silently assumed away.
28. **(Non-blocking, resolved)** This plan's own Constitution Check previously said "nothing new
    to test for reproducibility beyond what #5 already covers" — inaccurate, since `start_utc` and
    the new `detection_id` scheme are new deterministic outputs. Corrected below: the planned
    timestamp/ID determinism tests are required reproducibility evidence, not optional schema
    tests.

## Project Structure

### Documentation (this feature)

```text
specs/006-sensor-adapter-contract/
├── spec.md      # Feature specification (/speckit-specify output)
├── plan.md      # This file (/speckit-plan output)
└── tasks.md     # Task breakdown (/speckit-tasks output, not yet created)
```

### Source Code (repository root)

```text
src/
├── adapters/                   # EXISTING placeholder package (architecture.md §2); populated here
│   ├── __init__.py
│   ├── base.py                  # SensorAdapter protocol: translate(raw, sensor, scenario) -> list
│   ├── sensor1.py                # Concrete adapter for sensor 1
│   ├── sensor2.py                # Concrete adapter for sensor 2
│   └── messages.py               # Detection + Heartbeat pydantic models (architecture.md §3.1)
├── config/
│   └── models.py                 # EXTEND: SensorConfig gains heartbeat_timeout_s;
│                                  # ScenarioConfig gains start_utc
└── simulator/
    └── detections.py             # MINOR REFACTOR: extract expected_ticks(update_rate_hz,
                                   # duration_s) -> list[float], the formula already inlined in
                                   # generate_sensor_detections, so translate() can import and
                                   # reuse it verbatim (disposition item 15) — no behavior change,
                                   # existing #5 tests must still pass unmodified

config/
├── sensors/example_sensor.yaml   # UPDATE: add heartbeat_timeout_s
└── scenarios/example_scenario.yaml  # UPDATE: add start_utc
      # (verified against the actual repo layout — the plan's earlier draft wrongly assumed both
      # new fields belonged on the scenario file; heartbeat_timeout_s is a per-sensor field and
      # therefore belongs in config/sensors/example_sensor.yaml, not the scenario file)

tests/
├── test_detections.py             # UPDATE: existing fixtures construct SensorConfig/
│                                  # ScenarioConfig directly; must pass the new required fields
│                                  # (or the fields need sensible non-breaking defaults — decide
│                                  # per-field in tasks.md; heartbeat_timeout_s and start_utc are
│                                  # both good candidates for required-with-no-default, since
│                                  # silently defaulting start_utc would reintroduce the
│                                  # reproducibility risk this plan just fixed)
├── test_adapters.py              # NEW: schema conformance, both adapters, heartbeat semantics,
│                                  # detection_id uniqueness, timestamp_utc determinism,
│                                  # expected_ticks() coverage (t_s=0, non-binary-exact rate,
│                                  # non-exact final tick, equality with generate_sensor_detections'
│                                  # own t_s values), heartbeat_timeout_s validator rejection,
│                                  # off-schedule RawDetection.t_s raises, mismatched
│                                  # RawDetection.sensor_id raises (FR-011), isinstance-based
│                                  # Detection-only filtering of translate()'s output excludes
│                                  # Heartbeat (FR-012's contract, not an orchestrator/#13 test)
└── test_adapter_extensibility.py   # NEW: throwaway test adapter proving SensorAdapter alone
                                     # is sufficient to add a new sensor (spec User Story 2)
```

**Structure Decision**: Populate the existing `src/adapters/` placeholder package (confirmed via
rubber-duck review item 11 — it already exists per architecture.md §2, with an empty
`__init__.py`; this issue is not introducing a new package). `Detection` and `Heartbeat` live in
`src/adapters/messages.py` rather than `src/config/models.py`, since both are pipeline message
schemas (like `RawDetection` in `src/simulator/detections.py`), not YAML-loaded configuration —
confirmed sound by rubber-duck review item 10. The one deliberate exception to "adapters only
consume `RawDetection`, read-only" is the minimal, behavior-preserving `expected_ticks()`
extraction in `src/simulator/detections.py` (disposition item 15).

## Architecture doc update (to be made in the implementing PR, not this plan)

Once implementation is complete, the implementing PR must update architecture.md:
- §3.4: revise the wording itself (not just §13), since independent review found that leaving it
  unchanged would make the documented liveness guarantee *more* misleading once #6 ships, not
  less. New wording must state plainly: a `Heartbeat` means no `Detection` was produced for a
  nominal scheduled tick (schedule-coverage), and that this is **distinct from** detecting a
  genuinely silent/failed sensor, which remains unresolved (pointer to §13).
- §13: strike the heartbeat bullet, replace with a short "Resolved in #6" pointer: adapters emit
  an explicit `Heartbeat` message per architecture.md §3.4's revised wording, computed as a pure
  function of the sensor's scheduled tick cadence (via the shared `expected_ticks()` helper) —
  not the full reasoning above, which stays in this `plan.md`. Also *add three new* bullets (not
  previously tracked):
  - (surfaced by rubber-duck review item 6) `SensorConfig`'s single `update_rate_hz` field
    doesn't yet match §3.4's described `[min_hz, max_hz]` range — flagged for #7 (the harness,
    which owns the rate check) to resolve, not fixed retroactively here.
  - (surfaced by rubber-duck review item 13 — **the important one**) `Heartbeat` as designed in
    #6 proves schedule-coverage, not real liveness: it cannot distinguish "sensor alive, nothing
    to report" from "sensor silently stopped reporting," because `generate_sensor_detections`
    (#5) has no failure mode for it to fail to notice. The conformance harness's fault-injection
    check (§4 check 7, "dropped-message behavior") will need a mechanism to give `translate()`
    (or a successor) real evidence of actual feed coverage, not just the nominal schedule — open
    for #7 to resolve.
  - (surfaced by independent review, disposition item 24) §4 check 5's "measured inter-detection
    interval... falls within `[min_hz, max_hz]`" no longer cleanly applies once a sensor can
    produce long `Heartbeat`-only stretches with zero `Detection`s (no target in view) — the
    harness (#7) will need to measure cadence across `Detection | Heartbeat` messages, not
    `Detection` alone, to avoid an undefined or falsely-failing rate check during idle periods.
- §2: note `src/adapters/` is now populated (it was already listed as a placeholder).
- §3.1: note `Detection.detection_id` is deterministically generated as
  `f"{sensor_id}:{tick_index}:{index_within_tick}"` by the adapter, not provided by the sensor.
- §5: no wording change needed — its existing "Input: canonical `Detection` objects
  (post-harness-gate)" phrasing already means `Heartbeat` is excluded; #6 just makes that explicit
  in `plan.md`'s "Consumer boundary" (disposition item 23) rather than relying on an inference.
- No new §12 row — the `Heartbeat`-as-signal choice directly satisfies §3.4's already-locked
  wording rather than establishing a new locked decision at that level; it's recorded in this
  `plan.md` and pointed to from §13 instead.

## Complexity Tracking

Not applicable — no constitution violations identified above.
