# Implementation Plan: Sensor adapter contract (Detection schema + 2 known-good adapters)

**Branch**: `006-sensor-adapter-contract` | **Date**: 2026-10-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/006-sensor-adapter-contract/spec.md`

## Summary

Define the canonical `Detection`/`Heartbeat` pydantic messages and `SensorAdapter` protocol
(architecture.md §3.1-§3.3), implement two concrete adapters over one shared `translate()`
implementation — bound to sensor 1's existing config and a newly-created sensor 2 config
respectively (not two copies of the translation logic) — translating `RawDetection` output (from
#5, `src/simulator/detections.py`) into `Detection`/`Heartbeat` objects, and resolve the open
heartbeat/liveness design question (§13) by extending `SensorConfig` with a `heartbeat_timeout_s`
field and emitting an explicit `Heartbeat` message (not inferred adapter instance state) for any
scheduled tick with no matching `RawDetection` — see "Heartbeat design decision" below for the
full reasoning, rejected alternatives, and the honestly-scoped limitation this issue does *not*
solve (detecting a genuinely silent/failed sensor, deferred to #7). `Heartbeat` shares `Detection`'s
`timestamp_utc` time base (not simulator-relative `t_s` alone), and fusion never receives
`Heartbeat` entries — only the harness does.

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
  `heartbeat_timeout_s > 1 / update_rate_hz` (a tick's worth of slack, at minimum). Without this,
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
  `dropout_probability` dropped it), emit exactly one
  `Heartbeat(sensor_id=sensor.sensor_id, timestamp_utc=start_utc + t_s, t_s=t_s)` instead — using
  the identical `start_utc + t_s` conversion `Detection.timestamp_utc` uses, so `Heartbeat` and
  `Detection` share one time base (fixed after the opus-pinned review — see disposition item 31).
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

**Why this is now consistent with architecture.md §3.4's structure (wording to be refined, not
replaced)**: §3.4 already states an adapter "must emit a `Detection` (or an explicit
heartbeat/liveness signal...) within `heartbeat_timeout_s`." The revised design emits a literal,
named `Heartbeat` signal, satisfying the *emission* half of that sentence directly. **However**,
§3.4's trailing clause — "or the harness/fusion engine treats it as dead" — names fusion as a
consumer of the dead/alive determination, which conflicts with the Consumer boundary decision
above (fusion never receives `Heartbeat`, only the harness does). This is a genuine wording
conflict requiring an actual §3.4 edit, not just a §13 pointer — see "Architecture doc update"
below and disposition item 29 (added after the opus-pinned review caught this still unresolved).

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

1. **(Blocking, resolved — note added at review round 6)** First draft had no source of "empty
   ticks" from the batch-oriented simulator — resolved by having `translate()` independently
   recompute the identical tick schedule from public config fields (`update_rate_hz`,
   `duration_s`), requiring zero changes to `src/simulator/detections.py`'s own logic. (This claim
   is about the simulator's existing code, not about the test suite — item 15 separately requires
   updating `tests/test_detections.py`'s config fixtures once new required fields are added; the
   two are not in tension.)
2. **(Blocking, resolved)** Instance state wasn't observable by a batch-evaluating harness —
   resolved by making `Heartbeat` an explicit, emitted entry in the same returned list as
   `Detection`, fully observable from the completed output alone.
3. **(Blocking, resolved — revised again at item 29)** First draft conflicted with §3.4's locked
   "must emit... a signal" wording — resolved by actually emitting a named `Heartbeat` signal.
   (Original note here said "no architecture.md §3.4 amendment needed, only §13's pointer update"
   — **this was wrong**; see item 29 for why §3.4 itself does need an edit, caught by the
   opus-pinned review after this item had been marked resolved for 3 prior rounds.)
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
   harness (#7) will use for its clock-offset check — same source, fully reproducible. (The
   earlier claim that this hand-off is "trivial" was itself retracted at item 33: #7 still has to
   decide how it actually receives `start_utc` and simulator-time per `Detection`, since
   `raw_payload` is documented as debugging-only, not a load-bearing contract field.)
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
    `heartbeat_timeout_s > 1 / update_rate_hz`, rejected at config-load time rather than
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

A **fifth** review was run — per explicit user decision, as a separate agent pinned to an
opus-tier model (see `.github/copilot-instructions.md`'s "Agent roles and model assignment"),
specifically to re-check the prior 4 rounds' claimed resolutions against the actual current text,
not just trust their own "resolved" labels. It found that one claimed resolution (item 3) was
itself stale, plus 2 more new blocking issues and 5 non-blocking issues:

29. **(Blocking, resolved)** Architecture.md §3.4's locked wording ends "...or the
    **harness/fusion engine** treats it as dead" — naming fusion as a consumer of the dead/alive
    determination. This directly conflicts with the Consumer boundary decision (disposition item
    23: fusion never receives `Heartbeat`). Item 3 above had wrongly claimed "no §3.4 amendment
    needed" three rounds ago, and that stale claim survived unnoticed until this review actually
    re-checked it against the current design rather than trusting the old label. **Resolved**: the
    "Architecture doc update" section below now requires an actual §3.4 text edit (not just a §13
    pointer) dropping "fusion engine" from that clause — dead-sensor handling is the harness's job
    alone, consistent with FR-012.
30. **(Blocking, resolved)** `config/sensors/example_sensor.yaml` defines only `sensor-1`; there
    is no `sensor-2` config anywhere in the repo (the only "sensor-2" is a `model_copy` created
    inline in `tests/test_scenario.py`, not a real config). The plan's spec.md Assumptions
    incorrectly claimed sensor 2's config was "reused as-is." Worse, nothing in the plan said what
    would actually differ between `sensor1.py` and `sensor2.py` — since `translate()` takes
    `sensor: SensorConfig` as a parameter, two adapters calling the identical logic would be the
    same function duplicated twice, which Principle VII's architecture-health pass exists to
    catch. **Resolved**:
    - A real `config/sensors/sensor_2.yaml` is added, with a distinct `update_rate_hz`,
      `accuracy_m`, and position from sensor 1's, so the two sensors are genuinely different
      configurations, not a copy-paste.
    - The code shape is now explicit, and corrected after a sixth review round found the first
      attempt at this fix described invalid Python: `translate()` is one shared, generic function
      living in `src/adapters/base.py`. `SensorAdapter` is a `Protocol`, which Python does not let
      you instantiate (`SensorAdapter(translate=translate)` raises `TypeError`), so `sensor1.py`
      and `sensor2.py` are plain modules that each re-export `translate` alongside their own
      sensor's `SensorConfig` object loaded from its YAML file — nothing is "bound"; every call
      site still passes `(raw_detections, sensor, scenario)` explicitly. These two modules exist
      only so #13's orchestration has a name to import per sensor, not because the translation
      logic itself differs per sensor, and not to satisfy any "reachable by name" requirement in
      FR-002 (no such requirement exists there — that citation in the prior fix was incorrect and
      has been removed).
31. **(Blocking, resolved)** `Heartbeat` was specified as `Heartbeat(sensor_id, t_s)` — carrying
    only simulator-relative `t_s`, while `Detection` carries `timestamp_utc`. This means the two
    message types wouldn't share a time base: #8's clock-offset adapter would get correct
    `Heartbeat` times (no conversion needed) and buggy `Detection` times (as intended), but any
    consumer trying to reason about cadence across both types (the Known limitation's own
    recommendation, and the §4 check 5 ambiguity at item 24) would be mixing two different clocks
    silently. It also conflicts with architecture.md §3.3's requirement that message schemas make
    sense "as if sent over a network" — a simulator-relative `t_s` doesn't travel. **Resolved**:
    `Heartbeat` gains `timestamp_utc`, computed by the exact same `start_utc + t_s` conversion
    `Detection` uses (one shared helper, not two independent implementations — avoiding yet
    another duplicated-formula risk). `Heartbeat.t_s` is kept alongside it, explicitly labeled
    informational/debugging only (matching `Detection.raw_payload`'s existing "debugging only"
    convention from §3.1), not a contract field any consumer should rely on for timing logic.
32. **(Non-blocking, resolved — scope corrected at review round 6)** The
    `heartbeat_timeout_s >= 1/update_rate_hz` validator (item 18) allows a config where the
    comparison is satisfied only by floating-point luck at the exact boundary — a config with
    `heartbeat_timeout_s == 1/update_rate_hz` passes construction but could fail a strict
    `gap <= timeout` check downstream (#7) due to ordinary float64 rounding in repeated addition.
    **Resolved**: the validator now requires strict headroom —
    `heartbeat_timeout_s > 1/update_rate_hz` (not `>=`) — removing the exact-equality boundary
    case. This narrows the risk; it does not eliminate it — `start_utc` values around 1.7e9
    (current Unix epoch) have a float64 spacing of roughly 2.4e-7s, so a config whose
    `heartbeat_timeout_s` exceeds the boundary by less than that spacing could still trip an exact
    downstream comparison. Noted for #7: any cadence check it implements MUST use a small
    tolerance (not exact equality) when comparing timestamps, since float64 arithmetic on
    seconds-since-epoch values doesn't guarantee exact results — this tolerance requirement is the
    actual protection, not the strict `>` alone.
33. **(Non-blocking, resolved — scoped as a §13 question rather than a false claim)** Disposition
    item 9 asserted `scenario.start_utc` is "trivially handed off" to the harness as its
    clock-offset reference — but the harness's check 4 needs each detection's true *simulator*
    time (`t_s`) to compute an offset, and `Detection` has no field for it other than
    `raw_payload` (marked "debugging only" in §3.1) or decoding it back out of `detection_id`
    (which would make the ID format a hidden, undocumented contract). **Resolved**: item 9's
    "trivially handed off" claim is retracted as overstated; this plan does not invent a new
    `Detection` field to solve it, since that's arguably #7/#8's design decision, not #6's.
    Recorded as a new architecture.md §13 open question instead (see "Architecture doc update"):
    whether `raw_payload`'s `t_s` becomes a load-bearing contract field for the harness, or
    `Detection` needs an explicit simulator-time field after all.
34. **(Non-blocking, resolved)** The plan's proposed architecture.md §13 wording for check 5
    (added at disposition item 24: "measure cadence across `Detection | Heartbeat`") was itself
    unsound — `Heartbeat` entries are generated directly from `update_rate_hz`, so measuring
    cadence over a stream that includes them would just check the config against itself; any
    compliant adapter using `expected_ticks()` would trivially always pass, which is the same
    "can't actually fail" weakness the Known limitation already admits for check 6. **Resolved**:
    the "Architecture doc update" section below no longer prescribes that approach — it now
    records check 5's ambiguity as an open question for #7 to actually solve, without steering it
    toward an answer that's been shown not to work.
35. **(Non-blocking, resolved)** Two contradictions around tests and defaults:
    - The `expected_ticks()` extraction was described as behavior-preserving with "existing #5
      tests must still pass unmodified," while the Project Structure section separately lists
      `tests/test_detections.py` as needing updates for the new required fields. Both were true
      but about different changes conflated into one bullet, risking an implementer not knowing
      whether editing that test file would undermine the "extraction didn't change behavior"
      claim. **Resolved**: the `expected_ticks()` extraction is now explicitly its own, first
      commit/task in `tasks.md` (once written), verified against the *unmodified* existing test
      suite before any new required fields are added in a separate, later commit — so "extraction
      is behavior-preserving" stays independently checkable.
    - Whether `heartbeat_timeout_s`/`start_utc` get defaults was left to "decide per-field in
      tasks.md." **Resolved now, not deferred**: `start_utc` stays required with no default (a
      silent default would reintroduce the reproducibility risk this plan already fixed once).
      `heartbeat_timeout_s` also stays required with no default — unlike `lat`/`lon` in #5
      (where a sensible default, the defended area's center, actually exists), there is no
      non-arbitrary default timeout value, so forcing an explicit choice is correct, not an
      oversight.
36. **(Non-blocking, resolved — wording corrected at review round 6)** User Story 2's acceptance
    scenario said a new adapter is "registered and run," and FR-005 requires "implementing
    `SensorAdapter` plus a `SensorConfig` entry" — but no mechanism connects a `SensorConfig`
    entry to a specific adapter function anywhere in this plan (disposition item 7 explicitly says
    "no registration lifecycle"). Review round 6 also flagged that architecture.md §10's sequence
    diagram already uses "Register adapter" for a *different* step (submitting an adapter to the
    harness gate for conformance checking), so reusing "registered" here risked conflating two
    unrelated meanings. **Resolved**: spec.md's User Story 2 acceptance scenario now says
    "implemented and invoked directly," not "registered." The extensibility test
    (`test_adapter_extensibility.py`) calls the throwaway adapter's `translate()` directly — it
    does not exercise any config-to-adapter mapping, because none exists yet. The architecture.md
    §13 open question this plan adds is scoped narrowly to the *mapping from a `sensor_id` to its
    adapter function* (for #13/orchestration to resolve) — distinct from, and not in conflict
    with, §10's existing "Register adapter" harness-gate step.
37. **(Blocking, resolved)** A sixth rubber-duck round (opus-pinned, independent of round 5) found
    the previous round's fix for item 30 described code that doesn't run: `SensorAdapter` is a
    `Protocol`, and `SensorAdapter(translate=translate)` raises `TypeError` on instantiation; the
    cited "FR-002's reachable-by-name requirement" doesn't exist in FR-002's actual text. It also
    found five non-blocking staleness/consistency gaps: item 1 still said "zero changes to
    `src/simulator/`" in a way that read as contradicting item 15's test-fixture updates; item 9
    still called the harness clock-offset hand-off "trivial," which item 33 had already retracted;
    spec.md's FR-002 still listed "fusion engine" as an adapter caller, the same class of stale
    reference as B1; spec.md's User Story 2 still said "registered," conflicting with
    architecture.md §10's unrelated "Register adapter" step; and item 32's framing claimed the
    strict `>` validator removed the float-precision boundary risk "entirely," which overstates
    it — a config just inside the new boundary can still be closer than one float64 ULP. All six
    are fixed: item 30's code shape now uses plain module re-exports (no `Protocol` instantiation,
    no invented FR-002 citation); items 1, 9, and 32 now carry accurate, non-contradictory
    wording; FR-002 no longer lists fusion engine; spec.md's User Story 2 now says "implemented and
    invoked directly"; and the architecture.md update plan now also records the `Heartbeat` field
    table, the `translate()` signature, and the new config fields in §2/§3.1, not only in
    `plan.md`. This is the second time in six rounds that a "resolved" item was found to still be
    wrong on a later pass (item 3 at round 5, item 30/1/9/32 at round 6) — reinforcing why the
    re-review-after-substantive-revision rule, not a one-time pass, is the correct standard.

**Suggestion adopted (not a blocking/non-blocking finding, but incorporated directly)**: the
existing tick formula (`floor(duration_s/dt_s)+1`) can omit a final partial tick (e.g.
`duration_s=0.3` at 10 Hz yields ticks `[0, 0.1, 0.2]`, not `[0, 0.1, 0.2, 0.3]`) — this is
`generate_sensor_detections`'s existing, unchanged behavior, and `expected_ticks()` preserves it
faithfully rather than "fixing" an out-of-scope behavior. The item-22 test list is adjusted to not
assert the final tick always equals `duration_s`. `translate()` additionally asserts the ticks
returned by `expected_ticks()` are unique before using them as a lookup key, as a defensive
assertion against a future change to the shared formula silently breaking that invariant.

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
│   ├── base.py                  # SensorAdapter protocol + the one shared translate(raw, sensor,
│   │                             # scenario) -> list[Detection | Heartbeat] implementation
│   │                             # (disposition item 30, corrected at review round 6 — the two
│   │                             # adapters below don't duplicate logic; they re-export the same
│   │                             # translate() and each pair it with their own sensor's config,
│   │                             # not a "bound" instance of anything — translate() still takes
│   │                             # sensor/scenario as explicit arguments on every call)
│   ├── sensor1.py                # Re-exports base.translate + sensor 1's SensorConfig (loaded
│   │                             # from config/sensors/example_sensor.yaml)
│   ├── sensor2.py                # Re-exports base.translate + sensor 2's SensorConfig (loaded
│   │                             # from config/sensors/sensor_2.yaml)
│   └── messages.py               # Detection + Heartbeat pydantic models (architecture.md §3.1)
├── config/
│   └── models.py                 # EXTEND: SensorConfig gains heartbeat_timeout_s (validator:
│                                  # heartbeat_timeout_s > 1/update_rate_hz, required, no default);
│                                  # ScenarioConfig gains start_utc (required, no default)
└── simulator/
    └── detections.py             # MINOR REFACTOR: extract expected_ticks(update_rate_hz,
                                   # duration_s) -> list[float], the formula already inlined in
                                   # generate_sensor_detections, so translate() can import and
                                   # reuse it verbatim (disposition item 15) — no behavior change.
                                   # Land this as its OWN first commit/task, verified against the
                                   # existing #5 test suite UNMODIFIED, before the separate commit
                                   # that adds new required config fields (disposition item 35) —
                                   # keeps "extraction is behavior-preserving" independently
                                   # checkable rather than conflated with the config changes.

config/
├── sensors/
│   ├── example_sensor.yaml       # UPDATE: add heartbeat_timeout_s to existing sensor-1 entry
│   └── sensor_2.yaml             # NEW (disposition item 30 — did not exist before; a real,
│                                  # distinct update_rate_hz/accuracy_m/position from sensor-1's,
│                                  # not a copy, so the two adapters are genuinely exercising
│                                  # different configs, not identical ones)
└── scenarios/example_scenario.yaml  # UPDATE: add start_utc
      # (verified against the actual repo layout — the plan's earlier draft wrongly assumed both
      # new fields belonged on the scenario file; heartbeat_timeout_s is a per-sensor field and
      # therefore belongs in config/sensors/, not the scenario file)

tests/
├── test_detections.py             # UPDATE: existing fixtures construct SensorConfig/
│                                  # ScenarioConfig directly; must pass the new required fields
│                                  # explicitly — heartbeat_timeout_s and start_utc are both
│                                  # required with no default (disposition item 35), so there is
│                                  # no fallback to rely on; silently defaulting start_utc would
│                                  # reintroduce the reproducibility risk this plan already fixed
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
- §3.4: revise the wording itself (not just §13) — this needs two distinct fixes, both caught by
  review, not one:
  1. State plainly that a `Heartbeat` means no `Detection` was produced for a nominal scheduled
     tick (schedule-coverage), and that this is **distinct from** detecting a genuinely
     silent/failed sensor, which remains unresolved (pointer to §13).
  2. **Drop "fusion engine" from the trailing clause** ("...or the harness/fusion engine treats it
     as dead") — fusion never receives `Heartbeat` at all (Consumer boundary, disposition item
     23); dead-sensor handling is the harness's determination alone. Leaving "fusion engine" in
     that sentence would contradict the Consumer boundary decision in the architecture doc itself,
     which is exactly the self-contradiction the opus-pinned review caught at disposition item 29
     after 3 prior rounds missed it.
- §13: strike the heartbeat bullet, replace with a short "Resolved in #6" pointer: adapters emit
  an explicit `Heartbeat` message per architecture.md §3.4's revised wording, computed as a pure
  function of the sensor's scheduled tick cadence (via the shared `expected_ticks()` helper) —
  not the full reasoning above, which stays in this `plan.md`. Also *add five new* bullets (not
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
  - (surfaced by independent review item 24, **wording corrected at disposition item 34 — do not
    reuse the originally-proposed fix**) §4 check 5's "measured inter-detection interval... falls
    within `[min_hz, max_hz]`" no longer cleanly applies once a sensor can produce long
    `Heartbeat`-only stretches with zero `Detection`s. The earlier draft of this bullet suggested
    measuring cadence across `Detection | Heartbeat` together — **that doesn't work**, since
    `Heartbeat` is generated directly from the configured rate and would make the check
    unfalsifiable. Left open for #7 to actually solve, with that approach explicitly ruled out
    rather than silently left as the implied answer.
  - (surfaced by opus-pinned review item 33) whether `raw_payload`'s `t_s` field becomes a
    load-bearing contract the harness (#7) relies on for its clock-offset check (§4 check 4),
    since `Detection` has no dedicated simulator-time field today and decoding `t_s` back out of
    `detection_id` would make the ID format an undocumented, hidden contract. #6 does not resolve
    this; it's #7/#8's design decision.
  - (surfaced by opus-pinned review item 36, scope narrowed at review round 6) no mechanism maps
    a `SensorConfig`/`sensor_id` entry to the adapter function that should process it. This is
    distinct from §10's existing "Register adapter" sequence step (submitting an adapter to the
    harness gate for conformance checking) — the gap here is specifically the `sensor_id` →
    adapter-function lookup, not the harness-gate step, which already exists and is unaffected.
    Left for #13 (orchestration) to design.
- §2: note `src/adapters/` is now populated (it was already listed as a placeholder), and add a
  "Resolved during implementation" note recording the `SensorAdapter.translate` signature
  (`translate(raw_detections: list[RawDetection], sensor: SensorConfig,
  scenario: ScenarioConfig) -> list[Detection | Heartbeat]`) and the new `ScenarioConfig.start_utc`
  / `SensorConfig.heartbeat_timeout_s` config fields — matching the pattern #5 used for its own
  config additions, rather than leaving these contract details recorded only in `plan.md` where
  #7/#8/#13 are less likely to look.
- §3.1: note `Detection.detection_id` is deterministically generated as
  `f"{sensor_id}:{tick_index}:{index_within_tick}"` by the adapter, not provided by the sensor;
  also add a `Heartbeat` field table (`sensor_id`, `timestamp_utc`, `t_s` labeled debugging-only)
  alongside `Detection`'s existing one, since `Heartbeat` is a new message type #7/#8/#13 all need
  to know the shape of.
- §5: no wording change needed — its existing "Input: canonical `Detection` objects
  (post-harness-gate)" phrasing already means `Heartbeat` is excluded; #6 just makes that explicit
  in `plan.md`'s "Consumer boundary" (disposition item 23) rather than relying on an inference.
- No new §12 row — the `Heartbeat`-as-signal choice directly satisfies §3.4's already-locked
  wording rather than establishing a new locked decision at that level; it's recorded in this
  `plan.md` and pointed to from §13 instead.

## Complexity Tracking

Not applicable — no constitution violations identified above.
