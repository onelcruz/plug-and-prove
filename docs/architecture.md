# Plug-and-Prove Architecture

> **How to use this doc:** This is the single source of truth for the system's design. Before writing a new sub-issue under the [epic](https://github.com/onelcruz/plug-and-prove/issues/1), check here first — it defines the components, the contracts between them, and what's already decided vs. still open. If you make an architectural change while implementing a sub-issue, update this doc in the same pull request so it never drifts out of sync.

## 1. System overview and goals

Plug-and-Prove is an offline, fully-simulated demo proving that a counter-drone (C-UAS) system can:

1. Accept a **new sensor** through a documented adapter contract.
2. **Automatically verify** that sensor's integration with a conformance harness before trusting its data.
3. Fuse multiple sensors into **one clean, explainable air picture** on a TAK map.

Everything runs on a single laptop, offline, on simulated data (see [epic #1](https://github.com/onelcruz/plug-and-prove/issues/1) for full constraints: no real sensors, no cloud services, no RF emissions, no effector control).

A deliberately **out of scope for now, designed-for-later** item: a public, Azure-hosted web version of this demo for use on a website. The output layer (section 4) is kept swappable specifically so a future "web map" output adapter can be added without touching the simulator, adapters, harness, fusion, or classifier. No Azure work is planned as part of this epic.

## 2. Major components

| # | Component | Responsibility |
|---|-----------|-----------------|
| 1 | **Scenario Simulator** | Generates ground-truth target (drone), bird, and clutter trajectories, and per-sensor noisy detections, from a seeded YAML config. |
| 2 | **Sensor Adapters** | Translate each sensor's raw simulated output into the canonical `Detection` message defined by the adapter contract. One adapter per sensor. |
| 3 | **Conformance Harness** | Runs contract tests against an adapter's output *before* it is allowed to feed the fusion engine. Produces a pass/fail report. Acts as a gate, not a passive monitor. |
| 4 | **Tracker / Fusion Engine** | Associates detections across sensors into tracks (create/update/coast/delete), using a constant-velocity Kalman filter. |
| 5 | **Classifier** | Labels each track drone / bird / unknown with a confidence score and a one-line plain-language reason. |
| 6 | **Recommendation Engine** | For threat-classified tracks, produces a cue/recommendation record suitable for operator or defeat-system handoff (logged/displayed only — no real effector control). |
| 7 | **Output Adapters** | Pluggable sinks that consume tracks + recommendations. MVP ships one: CoT/TAK output over UDP. A future web-map output adapter can be added here without changing anything upstream. |
| 8 | **Test Record Writer** | Captures every run's scenario, seed, sensor config, harness results, and summary metrics to a timestamped file — the evidence artifact for SBIR claims. |
| 9 | **Orchestrator** | Loads config, seeds the RNG, registers adapters (gated by the harness), and drives the simulation tick loop end to end. |

Suggested package layout (for scoping future sub-issues, not a requirement):

```
plug-and-prove/
├── config/
│   ├── scenarios/        # scenario YAML (targets, birds, clutter, seed)
│   └── sensors/           # per-sensor YAML (accuracy, rate, dropout)
├── src/
│   ├── simulator/            # includes rng.py, the shared seeded-RNG utility
│   ├── adapters/           # one module per sensor adapter
│   ├── conformance/         # harness + individual checks
│   ├── fusion/              # tracker, Kalman filter, association
│   ├── classification/
│   ├── recommendation/
│   ├── output/
│   │   └── cot/             # MVP output adapter
│   ├── recordkeeping/        # test record writer
│   ├── config/               # pydantic models + YAML loader for config/*.yaml
│   └── orchestrator.py
├── docs/
│   └── architecture.md
├── runs/                     # generated test records (committed — see decision below)
└── tests/
```

**Resolved during implementation (issue #4):** a `src/config/` module (not listed in the
original layout) holds the `pydantic` models and YAML loader shared by every component that
reads `config/scenarios/*.yaml` or `config/sensors/*.yaml`. It's cross-cutting infrastructure,
not a pipeline stage, so it doesn't appear in the component table in §2 above. `runs/` is
committed (with a `.gitkeep` placeholder) rather than gitignored, resolving one of the open
questions in §13 — test-record files are small and are part of the demo's evidence trail, so
keeping them in version control by default is simpler than adding a separate export step. This
can be revisited if `runs/` grows large.

**Resolved during implementation (issue #5):** `ScenarioConfig` gained `duration_s` and
`drones`/`birds`/`clutter` lists (`DroneTarget`, `BirdTarget`, `ClutterConfig` models in
`src/config/models.py`) so target generation is fully YAML-driven, and `SensorConfig` gained
optional `lat`/`lon` (defaulting to the defended area's center when omitted, so existing sensor
configs remain valid unchanged). The simulator itself (`src/simulator/trajectories.py`,
`detections.py`, `scenario.py`) generates ground truth and per-sensor raw detections using a
simple flat-earth meters approximation (`src/simulator/geo.py`) — the same "small area" premise
as the fusion engine's internal ENU frame in §3.2, but applied here purely for simulation, not
exposed outside it. Raw detections use `t_s` (seconds since scenario start), not a UTC epoch
timestamp — converting to `timestamp_utc` (and optionally introducing a clock-offset bug) is
left to the adapter layer in #6/#8, consistent with the conformance harness owning
timestamp/clock-offset validation (§4).

**Resolved during implementation (issue #6):** `src/adapters/` is now populated: `base.py` holds
the `SensorAdapter` protocol and the shared `translate()` function (`translate(raw_detections:
list[RawDetection], sensor: SensorConfig, scenario: ScenarioConfig) -> list[Detection |
Heartbeat]`), and `sensor1.py`/`sensor2.py` are thin modules that re-export `translate` paired
with their own sensor's `SensorConfig`. `SensorConfig` gained `heartbeat_timeout_s` (validated
strictly greater than `1/update_rate_hz`), and `ScenarioConfig` gained a required `start_utc`
(a configured, deterministic Unix epoch float) — both follow the pattern #5 used for its own
config additions.

## 3. The sensor adapter contract

This is the extensibility seam: **adding a new sensor means writing one adapter module + one config entry — no changes to the harness, fusion engine, classifier, or output layer.**

### 3.1 Canonical `Detection` message

Every adapter must emit `Detection` objects with this schema (enforced with `pydantic`, which gives free, structured validation errors for the harness to report):

| Field | Type | Units / Format | Notes |
|---|---|---|---|
| `sensor_id` | str | — | Stable identifier for the reporting sensor |
| `detection_id` | str | — | Unique per detection |
| `timestamp_utc` | float | seconds since Unix epoch (UTC) | Must be within the configured max clock offset of simulator time |
| `lat` | float | decimal degrees, WGS84 | |
| `lon` | float | decimal degrees, WGS84 | |
| `alt_m` | float | meters, above ground level | |
| `accuracy_m` | float | meters, 1-sigma | Positive; used as measurement noise in the Kalman filter |
| `velocity_mps` | float, optional | meters/second | If the sensor provides Doppler/velocity |
| `confidence` | float, optional | 0.0–1.0 | Sensor's own detection confidence/SNR, if available |
| `raw_payload` | dict | — | Original untranslated sensor output, kept for debugging only |

**Resolved during implementation (issue #6):** `detection_id` is deterministically generated by
the adapter as `f"{sensor_id}:{tick_index}:{index_within_tick}"` (scheduled-tick index, then
within-tick insertion order), not supplied by the sensor itself.

**Resolved during implementation (issue #6):** adapters also emit an explicit `Heartbeat`
message for any scheduled tick with no `Detection` (see §3.4):

| Field | Type | Units / Format | Notes |
|---|---|---|---|
| `sensor_id` | str | — | Stable identifier for the reporting sensor |
| `timestamp_utc` | float | seconds since Unix epoch (UTC) | Same `start_utc + t_s` time base as `Detection` |
| `t_s` | float | seconds since scenario start | Debugging only, like `Detection.raw_payload` — not a contract field any consumer should rely on |

### 3.2 Coordinate frame (decision locked)

- **At the edges** (adapter output, TAK output): WGS84 latitude/longitude/altitude — the real-world standard sensors and TAK both use.
- **Internally** (inside the fusion engine): converted to a local flat ENU (east-north-up, meters) frame relative to a fixed origin (the defended area's center). Kalman filter math is simpler and more numerically stable in flat meters over the small area this demo covers.
- Conversion between WGS84 and local ENU happens at the fusion engine's input/output boundary — adapters and the output layer never need to know about ENU.

### 3.3 Transport (decision locked)

- Adapters are in-process Python objects (function calls / direct method invocation), **not** real network sockets, for this demo. Everything runs in one program on one laptop; real network transport would add failure modes we don't need yet.
- The `Detection` schema is still designed as if it could be serialized over a network (plain field types, no in-memory-only references), so a future adapter for a real networked sensor is a drop-in, not a redesign.

### 3.4 Update rate & heartbeat

- Each sensor config declares an expected update-rate range (e.g. `min_hz`, `max_hz`) and a `heartbeat_timeout_s`.
- An adapter must account for every scheduled tick with a `Detection` or an explicit `Heartbeat` message. The harness treats it as dead if neither message arrives within `heartbeat_timeout_s`.

**Resolved during implementation (issue #6):** a `Heartbeat` means *no `Detection` was produced
for a nominal scheduled tick* (schedule-coverage) — it is **distinct from** detecting a
genuinely silent/failed sensor, which remains unresolved (see §13). `Heartbeat` is computed as a
pure function of the sensor's scheduled tick cadence (via the shared `expected_ticks()` helper),
not real liveness/failure detection: `translate()` has no way to observe whether the upstream
feed was actually still being produced, only whether a tick's scheduled slot was filled.
`Heartbeat` is consumed only by the conformance harness, never the fusion engine — this is
narrower than the earlier "harness/fusion engine treats it as dead" wording, which is dropped
here because it contradicted §5's existing "canonical `Detection` objects (post-harness-gate)"
input contract, which already excludes `Heartbeat` from fusion's input.

## 4. The conformance harness (decision locked: pre-ingest gate)

The harness runs as a **gate**, not a passive sidecar: a sensor's adapter must pass every check below before its detections are allowed into the fusion engine. This matches the demo narrative directly — sensor 3 is added, fails on a bad timestamp, and only joins the live picture after the fix and a passing re-run.

Concrete checks (pytest-style, one pass/fail result each, aggregated into a Markdown/HTML report):

1. **Schema** — every `Detection` validates strictly against the pydantic model (required fields, correct types), carries the submitted sensor's `sensor_id`, and has a `detection_id` unique within its run.
2. **Units** — `alt_m` and `accuracy_m` fall within plausible configured bounds; no unit confusion (e.g. feet reported as meters).
3. **Coordinate frame** — every `Detection` lies within `range_m + 6 × accuracy_m` of the sensor's position (WGS84), catching gross frame/projection errors without rejecting correct detections outside the defended area.
4. **Timestamp validity & clock offset** — `timestamp_utc` is not in the future beyond a small tolerance, is not stale, and its offset from simulator reference time is within `max_clock_offset_s`. **This is the check the demo deliberately fails** (sensor 3 ships with an injected timestamp offset bug).
5. **Update rate** — measured inter-detection interval over a short sample window falls within the sensor's configured `[min_hz, max_hz]`.
6. **Heartbeat / liveness** — a `Detection` or heartbeat signal arrives within `heartbeat_timeout_s`.
7. **Dropped-message behavior** — the harness withholds a run of raw inputs and confirms the adapter does not crash, emits a `Heartbeat` at every withheld tick, and neither fabricates nor duplicates `Detection`s. Fusion coasting through such a gap is verified in #9.

The harness completes in under 60 seconds (epic acceptance criterion) and produces a report listing each check as pass/fail with a one-line reason — mirroring the classifier's "explainable" philosophy.

Design details for the implementation: `specs/007-conformance-harness/`.

## 5. Tracker / fusion engine (decision locked: hand-rolled, not Stone Soup)

- A custom constant-velocity Kalman filter per track, implemented directly with `numpy`.
- Rejected Stone Soup (a full tracking framework) for this MVP: its value is handling dozens of edge cases this scripted, time-boxed demo doesn't need. Given the ~25–40 hour budget, a few hundred lines of purpose-built filter code is faster to get right, easier to explain in this doc, and easier to debug on camera than learning and correctly configuring a large framework. Stone Soup remains a documented option if the tracker needs to grow significantly later.
- Responsibilities: data association (nearest-neighbor/gating) across sensors, track creation, update, coasting (through brief dropouts), and deletion (track goes stale).
- Input: canonical `Detection` objects (post-harness-gate, converted to local ENU). Output: canonical `Track` objects (position, velocity, covariance, in both ENU and WGS84).

## 6. Classifier

- Rule-based (not ML/LLM — explicitly out of scope per the epic), operating on track kinematics: speed, acceleration/maneuver pattern, altitude band, path straightness vs. erratic movement.
- Output per track: label (`drone` / `bird` / `unknown`), a confidence score, and a one-line human-readable reason (e.g. "steady altitude and speed inconsistent with bird flight").

## 7. Recommendation engine

- For any track classified as a likely threat (drone, above a confidence threshold, within/approaching the defended area), emits a cue record: track ID, timestamp, position, classification, confidence, reason, and a placeholder suggested action.
- Logged and displayed only. No connection to any real effector or defeat system.

## 8. Output adapters (decision locked: direct CoT, no FreeTAKServer for MVP)

- MVP output adapter converts `Track` and recommendation records into Cursor-on-Target (CoT) XML events and sends them directly over UDP to a single TAK client (ATAK-CIV or WinTAK) on the same machine/network.
- Rejected FreeTAKServer (a relay/server for multiple TAK clients) for the MVP: the demo only needs one viewer on one map; a server to install, configure, and keep alive adds operational complexity with no payoff for a single scripted recording.
- **Extension point:** the output layer is intentionally an interface (`OutputAdapter`) that the fusion/classification/recommendation pipeline doesn't know the concrete type of. A future web-map output adapter (e.g., FastAPI + Leaflet, optionally Azure-hosted) can be added here later as its own separate effort, without modifying anything upstream. This is a deliberate non-goal for the current epic.

## 9. Test record writer

- Wraps each full run and writes a timestamped file capturing: date, scenario name and seed, sensor configuration (including which sensors passed/failed the harness and when), measured results (track counts, false-track rate before/after fusion, classification outcomes), and method (how the numbers were produced).
- This file is the artifact referenced in the epic's "SBIR evidence" purpose — it must be reproducible from a fixed seed.

## 10. End-to-end data flow (maps to the epic's demo scenario steps 1–6)

```mermaid
sequenceDiagram
    participant Cfg as Scenario Config (YAML)
    participant Sim as Scenario Simulator
    participant A1 as Adapter (Sensor 1 & 2)
    participant Harness as Conformance Harness
    participant Fusion as Tracker / Fusion Engine
    participant Classifier as Classifier
    participant Rec as Recommendation Engine
    participant Out as CoT Output Adapter
    participant TAK as TAK Client
    participant Rec2 as Test Record Writer
    participant A3 as Adapter (Sensor 3, new)

    Cfg->>Sim: Load scenario + seed
    Sim->>A1: Raw detections (sensors 1 & 2)
    A1->>Harness: Register adapter
    Harness-->>A1: PASS (already-conformant sensors)
    A1->>Fusion: Canonical Detections
    Fusion->>Classifier: Tracks
    Classifier->>Rec: Classified tracks (label, confidence, reason)
    Rec->>Out: Tracks + recommendations
    Out->>TAK: CoT events (live picture, 2 sensors)

    Note over A3,Harness: Sensor 3 added live, with injected timestamp offset bug
    Sim->>A3: Raw detections (sensor 3)
    A3->>Harness: Register adapter
    Harness-->>A3: FAIL (timestamp/clock-offset check)
    Note over Fusion: Sensor 3 NOT registered — picture unchanged

    Note over A3: Timestamp offset corrected
    A3->>Harness: Re-run conformance checks
    Harness-->>A3: PASS
    A3->>Fusion: Canonical Detections (now trusted)
    Fusion->>Classifier: Updated tracks (3 sensors)
    Classifier->>Rec: Classified tracks
    Rec->>Out: Tracks + recommendations
    Out->>TAK: CoT events (improved picture, 3 sensors)

    Sim->>Rec2: Run metadata, seed, config
    Harness->>Rec2: Pass/fail history
    Fusion->>Rec2: Track/classification metrics
    Rec2->>Rec2: Write timestamped test record file
```

Sensor 3's fail → fix beat is implemented in #8: see `specs/008-sensor3-clock-offset/`.

## 11. Component view

```mermaid
graph TD
    Cfg["Scenario + Sensor Config (YAML)"] --> Sim["Scenario Simulator"]
    Sim -->|raw detections| Adapters["Sensor Adapters (one per sensor)"]
    Adapters -->|canonical Detection| Harness{"Conformance Harness (gate)"}
    Harness -- PASS --> Fusion["Tracker / Fusion Engine (Kalman filter)"]
    Harness -- FAIL --> Report["Pass/Fail Report"]
    Fusion -->|Track| Classifier["Classifier (label + confidence + reason)"]
    Classifier -->|classified Track| RecEngine["Recommendation Engine"]
    RecEngine -->|Track + cue record| OutAdapter["Output Adapter: CoT/TAK (MVP)"]
    OutAdapter -->|CoT events, UDP| TAK["TAK Client (ATAK-CIV / WinTAK)"]
    RecEngine -.future, out of scope.-> WebAdapter["Output Adapter: Web Map (future)"]

    Sim --> Recorder["Test Record Writer"]
    Harness --> Recorder
    Fusion --> Recorder
    Classifier --> Recorder
    Recorder --> RunFile["Timestamped Test Record File"]

    classDef future fill:#eee,stroke:#999,stroke-dasharray: 5 5;
    class WebAdapter future;
```

## 12. Key design decisions (locked)

| # | Decision | Alternative considered | Why |
|---|---|---|---|
| 1 | WGS84 lat/lon/alt at component edges; local ENU meters internally for fusion math | Single frame throughout | Simpler, more numerically stable tracker math; matches real-world sensor/TAK conventions at the boundaries |
| 2 | In-process Python objects (pydantic-validated) for adapter transport | Real network sockets between components | No networking failure modes needed for a single-laptop demo; schema still designed to be serializable later |
| 3 | Conformance harness is a pre-ingest **gate** | Passive sidecar monitor that just reports | Matches the demo narrative exactly: bad sensor data is blocked before reaching the operator picture, not reported after the fact |
| 4 | Hand-rolled constant-velocity Kalman filter via `numpy` | Stone Soup tracking framework | Faster to build correctly and explain within the ~25–40 hour budget; Stone Soup's extra capability isn't needed for a scripted demo |
| 5 | Direct CoT over UDP to one TAK client | FreeTAKServer as relay/server | Only one viewer is needed for the MVP; avoids standing up and maintaining a server for no demo benefit |
| 6 | Public, Azure-hosted web version is explicitly deferred | Build hosted version now alongside MVP | Out of scope for the 11/8 deadline; output layer is kept swappable so it's a clean follow-on, not a rebuild |

## 13. Open questions / risks (to resolve in later sub-issues, not this spike)

- Exact bounding box / geographic parameters for the "defended area" used in the scenario config.
- Precise classifier thresholds (speed/altitude/maneuver bands) that separate drone vs. bird vs. unknown — needs tuning against the simulator's actual noise model.
- Exact definition and calculation of the "false threat track" metric used in the before/after fusion comparison (epic acceptance criterion).
- CoT event type codes and update-rate throttling to TAK (avoid flooding the client).

~~Whether heartbeat is a distinct message type or inferred from detection cadence for sensors
with no target in view.~~ **Resolved in #6:** adapters emit an explicit `Heartbeat` message per
§3.4's revised wording, computed as a pure function of the sensor's scheduled tick cadence (via
the shared `expected_ticks()` helper) — see `specs/006-sensor-adapter-contract/plan.md` for the
full design reasoning. This resolution opens five new, narrower questions:

- ~~`SensorConfig`'s single `update_rate_hz` field doesn't yet match §3.4's described `[min_hz,
  max_hz]` range — left for #7 (the conformance harness, which owns the rate check) to resolve.~~
- ~~`Heartbeat` as designed in #6 proves schedule-coverage, not real liveness: it cannot
  distinguish "sensor alive, nothing to report" from "sensor silently stopped reporting,"
  because the simulator (#5) has no failure mode for it to fail to notice. The conformance
  harness's fault-injection check (§4 check 7, "dropped-message behavior") will need a
  mechanism to give `translate()` (or a successor) real evidence of actual feed coverage, not
  just the nominal schedule — open for #7 to resolve.~~
- ~~§4 check 5's "measured inter-detection interval... falls within `[min_hz, max_hz]`" no longer
  cleanly applies once a sensor can produce long `Heartbeat`-only stretches with zero
  `Detection`s. Measuring cadence across `Detection | Heartbeat` together does **not** work,
  since `Heartbeat` is generated directly from the configured rate and would make the check
  unfalsifiable — left open for #7 to actually solve, with that approach explicitly ruled out.~~
- ~~Whether `raw_payload`'s `t_s` field (or `Heartbeat.t_s`) becomes a load-bearing contract the
  harness (#7) relies on for its clock-offset check (§4 check 4), since `Detection` has no
  dedicated simulator-time field today and decoding `t_s` back out of `detection_id` would make
  the ID format an undocumented, hidden contract. #6 does not resolve this; it's #7/#8's design
  decision.~~
- No mechanism maps a `SensorConfig`/`sensor_id` entry to the adapter function that should
  process it. This is distinct from §10's existing "Register adapter" sequence step (submitting
  an adapter to the harness gate for conformance checking) — the gap here is specifically the
  `sensor_id` → adapter-function lookup, not the harness-gate step, which already exists. Left
  for #13 (orchestration) to design.

**Resolved in #7** (the four struck bullets in the list above) — see `specs/007-conformance-harness/research.md`
(R2, R3, R5, R7): `min_hz`/`max_hz` live on `SensorConfig`; real gap evidence comes from
harness-withheld probe ticks; check 5 measures `Detection`-only cadence on a probe stream;
`raw_payload["t_s"]` stays debugging-only because the harness supplies and knows each input's time.

~~Whether `runs/` (test record output) is committed to the repo or gitignored.~~ **Resolved in
#4:** committed, with a `.gitkeep` placeholder — see §2.

## 14. Definition of done for this spike

This document plus the two Mermaid diagrams above are the complete deliverable for [issue #2](https://github.com/onelcruz/plug-and-prove/issues/2). Once merged, sub-issues for the simulator, adapter contract implementation, conformance harness, fusion engine, classifier, recommendation engine, CoT output, and test record writer can be drafted by referencing this doc directly, with no further architecture discussion required.
