# Contract: `src/conformance` public API (#7)

In-process Python API (§3.3). Consumers: the orchestrator (#13), the test record writer (#13/§9),
and #8's sensor-3 demo. Types are defined in [data-model.md](../data-model.md).

## Checks — `src/conformance/checks.py`

Pure functions over evidence; each returns exactly one `CheckResult` and never raises for bad
adapter output.

```text
check_schema(runs: Sequence[Sequence[object]], sensor_id: str) -> CheckResult             # 1
check_units(detections, sensor: SensorConfig, scenario: ScenarioConfig) -> CheckResult    # 2
check_coordinate_frame(detections, sensor, scenario) -> CheckResult                       # 3
check_clock_offset(runs: Sequence[tuple[list[RawDetection], list[Detection]]],
                   scenario) -> CheckResult                                               # 4
check_update_rate(full_probe_detections, sensor) -> CheckResult                           # 5
check_heartbeat(full_probe_messages, sensor, scenario) -> CheckResult                     # 6
check_dropped_messages(gap_probe_messages, gap_inputs: Sequence[RawDetection],
                       withheld_ticks_s: Sequence[float], sensor, scenario)
                   -> CheckResult                                                         # 7
```

Measurement rules are in [research.md](../research.md) R2–R8. Checks 5–7 are invariant to a
constant `timestamp_utc` offset.

## Probes — `src/conformance/probes.py`

```text
probe_position(sensor, scenario) -> tuple[float, float, float]      # lat, lon, alt_m
withheld_tick_indices(sensor, scenario) -> frozenset[int]
withheld_ticks_s(sensor, scenario) -> list[float]                   # sorted withheld tick times
build_probe_stream(sensor, scenario, withheld: frozenset[int] = frozenset()) -> list[RawDetection]
```

Deterministic; no RNG.

## Harness — `src/conformance/harness.py`

```text
run_harness(adapter: SensorAdapter, sensor: SensorConfig, scenario: ScenarioConfig,
            real_raw: list[RawDetection]) -> HarnessRun
```

`HarnessRun` = `(result: HarnessResult, real_detections: list[Detection])`. It calls `adapter`
three times (real, full probe, gap probe) and runs all 7 checks. It never raises because of adapter
or check behavior (FR-012).

## Gate — `src/conformance/gate.py`

```text
class ConformanceGate:
    submit(adapter, sensor, scenario, real_raw) -> HarnessResult
    admitted_detections(sensor_id: str) -> list[Detection]     # [] unless latest verdict admitted
    results() -> list[HarnessResult]                           # latest per sensor, submit order
```

This is the only supported path from an adapter's output to downstream consumers (§12 row 3).
`Heartbeat`s are never returned.

## Report — `src/conformance/report.py`

```text
render_markdown(results: Sequence[HarnessResult]) -> str
```

Per adapter: `## <sensor_id> — ADMITTED|BLOCKED`, then `| # | Check | Result | Reason |` with 7
rows. Byte-identical output for identical input.

## Import-boundary contract (`.importlinter`)

Established by prerequisite #26 (PR #27), not changed by #7:

- `no-ground-truth-leak` source modules: `src.adapters`, `src.conformance`, and the other
  downstream packages. Forbidden: `src.simulator.trajectories`, `src.simulator.scenario`.
- `[importlinter] exclude_type_checking_imports = True`.
- `detection-schema-truth-free` unchanged.
