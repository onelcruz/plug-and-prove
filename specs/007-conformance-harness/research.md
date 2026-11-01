# Research: Conformance harness (#7)

Decisions below resolve every open item from spec.md (Clarifications, Session 2026-10-31) and the
§13 bullets assigned to #7. Each lists the decision, why, and what was rejected.

## R1 — Check 7 is adapter-side (spec Q1)

- **Decision**: The harness withholds raw input for a contiguous run of probe ticks and verifies the
  adapter's response by counts: `Detection` count == raw inputs supplied, `Heartbeat` count ==
  withheld ticks, no duplicate `detection_id`, no exception.
- **Rationale**: The harness gates *adapters*. Fusion coasting is a fusion property and cannot
  distinguish a good adapter from a bad one. The fusion-side test moved to #9 (acceptance criterion
  added to issue #9).
- **Rejected**: splitting check 7 into a child issue blocked by #9; defining a consumer interface
  for #9 inside #7 (pre-designs #9's API).

## R2 — Clock-offset reference is harness-side (spec Q2)

- **Decision**: For every adapter run, reference times are `scenario.start_utc + raw.t_s` for each
  raw input the harness supplied. Sorted references are compared pairwise with sorted
  `Detection.timestamp_utc` values. Count mismatch → FAIL. Worst |difference| > `max_clock_offset_s`
  → FAIL, reason names direction ("ahead"/"behind"), magnitude, and limit.
- **Rationale**: Nothing the adapter under test emits is trusted as its own reference. Resolves §13
  bullet (d): `raw_payload["t_s"]` stays debugging-only.
- **Rejected**: `raw_payload["t_s"]` as contract (adapter-supplied, can be wrong in the same way);
  new `Detection.sim_time_s` field (same trust problem plus a §3.1 schema change).
- **Accepted limitation**: this reference works only because the harness supplies the inputs
  in-process. A real networked sensor (whose raw feed the harness does not generate) would need a
  different reference (e.g. a trusted time source or a known-time calibration target). Out of scope
  for this demo (§3.3, §12 row 2).

## R3 — Input model: real stream + deterministic probe streams (spec Q3)

- **Decision**: Each adapter is run on three inputs:
  1. **Real stream** — the caller's `RawDetection` list for that sensor (from the simulator).
  2. **Full probe** — one `RawDetection` at *every* scheduled tick (`expected_ticks`).
  3. **Gap probe** — the full probe with a contiguous run of **withheld ticks**.
  Checks 1–4 evaluate outputs of all three runs; checks 5–7 evaluate probe runs only (5 and 6: full
  probe; 7: gap probe).
- **Probe position**: due east of the sensor by `range_m / 2` (via `src.simulator.geo.offset_to_latlon`),
  altitude `(min_alt_m + max_alt_m) / 2`, `accuracy_m = sensor.accuracy_m`. Inside check 3's coverage
  bound and check 2's units bounds by construction. No randomness (Principle V).
- **Gap run**: length `k = ceil(2 × heartbeat_timeout_s × update_rate_hz)` ticks, starting at tick
  index `n // 3`, clamped so at least one tick remains supplied before and after the run. Spanning
  more than `heartbeat_timeout_s` means an adapter that silently skips withheld ticks also loses the
  Heartbeat count.
- **Resolves** §13 (b) (real gap evidence = harness-withheld ticks, not the nominal schedule) and
  (c) (check 5 measures `Detection`-only rate on a stream where the target is always in view).
- **Rejected**: real stream only (checks 5–7 unevaluable when no target is in view); probes only
  (never exercises realistic noisy multi-target data).

## R4 — Check 3 bound = sensor coverage circle (spec Q4)

- **Decision**: FAIL if `distance_m(sensor_pos, detection) > range_m + 6 × accuracy_m`. Sensor
  position = configured `lat`/`lon`, else defended-area center (same rule as the simulator).
- **Rationale**: The simulator range-gates on *true* distance, then adds per-axis Gaussian noise
  (σ = `accuracy_m`); radial noise is Rayleigh, so P(r > 6σ) = e^(−18) ≈ 1.5 × 10⁻⁸ per detection.
  Gross frame errors (swapped lat/lon, radians, sign-flipped lon) land kilometers to thousands of
  kilometers away.
- **Rejected**: literal defended-area radius (false-fails the drone at 3000 m vs `radius_m` 2000 m);
  defended area + configured margin (an extra tuned number).

## R5 — Conformance limits in config (spec Q5)

- **Decision**:
  - `SensorConfig` (+ required): `min_hz`, `max_hz`, `max_accuracy_m`. Validators:
    `min_hz <= update_rate_hz <= max_hz`, `accuracy_m <= max_accuracy_m`.
  - `ScenarioConfig` (+ required): `max_clock_offset_s` (positive), `min_alt_m` (≥ 0, AGL),
    `max_alt_m` (positive). Validators: `min_alt_m < max_alt_m`; every configured drone/bird/clutter
    `altitude_m` lies within `[min_alt_m, max_alt_m]` (guards against configs that guarantee a
    check-2 false fail).
- **YAML values**:

  | File | Field | Value | Why |
  |---|---|---|---|
  | `example_sensor.yaml` (sensor-1, 2 Hz, σ 15 m) | `min_hz` / `max_hz` | 1.5 / 2.5 | ±25 % band around nominal |
  | | `max_accuracy_m` | 50.0 | well above 15 m |
  | `sensor_2.yaml` (5 Hz, σ 8 m) | `min_hz` / `max_hz` | 4.0 / 6.0 | ±20 % band |
  | | `max_accuracy_m` | 50.0 | well above 8 m |
  | `example_scenario.yaml` | `max_clock_offset_s` | 0.5 | sub-tick for both sensors; any whole-second skew fails |
  | | `min_alt_m` / `max_alt_m` | 0.0 / 200.0 | drone 120 ± 2 m, bird 40 ± 1 m, clutter 50 m fit; drone in feet (394) fails |

- **Rationale**: user decision — system acceptance limits live on the scenario so a sensor cannot
  loosen the bar it is tested against (#8). Resolves §13 (a).
- **Noted risk (accepted)**: `min_hz`/`max_hz`/`max_accuracy_m` remain sensor-declared by design —
  they describe the sensor's own spec, and checks 2/5 verify the adapter honors that declaration.

## R6 — Import boundary fix (planning-time decision)

- **Decision** (delivered by #26 / PR #27, not by #7): In `src/simulator/detections.py`, move `from src.simulator.trajectories import
  TruthObject` under `if TYPE_CHECKING:` (it is used only in an annotation, and
  `from __future__ import annotations` is already active). Add `exclude_type_checking_imports = True`
  to `[importlinter]`. Re-add `src.adapters` to `no-ground-truth-leak` and drop the now-stale
  exclusion comment.
- **Evidence** (prototyped and reverted during planning): conformance → `simulator.detections`
  KEPT (2 kept, 0 broken); conformance → `simulator.trajectories` BROKEN; ruff clean; 43 passed.
- **Split out (analyze finding D1)**: Principle IV requires out-of-package gaps to be filed
  separately, so this change is delivered by **#26 (PR #27)**, and #7 is blocked by it. #7 makes no
  edits to `src/simulator/` or `.importlinter`.
- **Rejected**: moving `RawDetection`/`expected_ticks` to a new module; dependency-injecting the raw
  type and tick function; removing `src.conformance` from the contract.

## R7 — Offset invariance of checks 5–7 (spec FR-009a)

- **Decision**:
  - Check 5: `rate = (n − 1) / (t_last − t_first)` over full-probe `Detection` timestamps; needs n ≥ 2.
  - Check 6: sort full-probe messages by `timestamp_utc`; FAIL if any consecutive gap >
    `heartbeat_timeout_s`, or if `(scheduled_span − output_span) > heartbeat_timeout_s`.
  - Check 7: counts (R1), plus Heartbeat coverage of the withheld ticks after removing the constant
    offset estimated from the Detections; matched in sorted order within half a tick period
    (FR-009b, PR #28 review F3).
  - Check 5 compares `[min_hz, max_hz]` allowing for one `math.ulp` of timestamp resolution (FR-006).
- **Rationale**: A constant offset leaves counts, intervals, and spans unchanged (and check 7 removes it before
  comparing to the schedule), so the
  clock-offset fixture (and #8's sensor 3) fails only check 4 (SC-002).

## R8 — Schema check

- **Decision**: For every message from every run: if it is a `Detection` or `Heartbeat` instance,
  re-validate strictly with `type(m).model_validate(m.model_dump(), strict=True)` (catches objects built with
  `model_construct`/`model_copy(update=...)`, which skip validation); any other type FAILS. Also FAIL
  if no `Detection` was produced across all runs ("no Detections to evaluate" — vacuous truth is not
  evidence). Also FAIL on a `sensor_id` other than the submitted sensor's and on a `detection_id`
  repeated within one run (FR-002a/002b). Checks 2–7 use the instances as emitted (no re-validation), so a schema-only fault does
  not cascade.

## R9 — Failure isolation

- **Decision**: Each adapter run is wrapped; if it raises, every check that depends on that run's
  output FAILS with `adapter raised <ExcType>: <first line of message>`. Each check call is also
  wrapped; an unexpected exception inside a check yields FAIL for that check only (FR-012).
- **Reasons** are normalized to a single non-empty line (validator on `CheckResult`).

## R10 — Report

- **Decision**: Markdown only. Per adapter: heading `## <sensor_id> — ADMITTED|BLOCKED`, then a table
  `| # | Check | Result | Reason |` with exactly 7 rows. `|` in reasons is escaped. No wall-clock
  timestamps, so output is byte-identical for identical inputs. Persisting to `runs/` is #13's job.

## R11 — architecture.md update scope

- **Decision**: Per `.github/copilot-instructions.md` ("Add only a one-line pointer"), detail stays in
  this folder. architecture.md gets: (1) a one-line pointer under §4 to `specs/007-conformance-harness/`;
  (2) in-place minimal rewording of §4 checks 3 and 7 (otherwise the doc would state something false);
  (3) the four §13 bullets assigned to #7 struck through with one "Resolved in #7" pointer line.
  §12 is not touched. **Confirmed by the maintainer (2026-10-31, analyze finding I1)**: the
  "one-line pointer" rule governs where detail lives; the "update architecture.md when you resolve a
  §13 question or deviate" rule requires the minimal in-place corrections in (2) and (3).
