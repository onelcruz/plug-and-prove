"""Run an adapter through the seven contract checks (architecture.md §4).

The adapter is called three times -- on the caller's real stream, on a full probe
(one input per scheduled tick) and on a gap probe (a contiguous run of ticks
withheld) -- and the evidence is routed to the checks per research.md R3. An
exception raised by the adapter or by a check never escapes: it makes only the
dependent checks FAIL (FR-012).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from src.adapters.base import SensorAdapter
from src.adapters.messages import Detection, Heartbeat
from src.config.models import ScenarioConfig, SensorConfig
from src.conformance import checks
from src.conformance.probes import build_probe_stream, withheld_tick_indices
from src.conformance.results import CHECK_NAMES, CheckResult, HarnessResult
from src.simulator.detections import RawDetection


@dataclass(frozen=True)
class HarnessRun:
    """A verdict plus the real-stream ``Detection``s the gate may release if it is admitted."""

    result: HarnessResult
    real_detections: list[Detection]


@dataclass(frozen=True)
class _Outcome:
    """What one adapter call produced: its messages, or the failure that replaced them."""

    messages: list[Detection | Heartbeat]
    error: str | None = None


def _describe(prefix: str, exc: Exception) -> str:
    lines = str(exc).splitlines()
    first_line = lines[0].strip() if lines else ""
    suffix = f": {first_line}" if first_line else ""
    return f"{prefix} {type(exc).__name__}{suffix}"


def _call(
    adapter: SensorAdapter,
    raw: list[RawDetection],
    sensor: SensorConfig,
    scenario: ScenarioConfig,
) -> _Outcome:
    try:
        return _Outcome(messages=list(adapter(list(raw), sensor, scenario)))
    except Exception as exc:  # any adapter failure is a verdict, not a crash
        return _Outcome(messages=[], error=_describe("adapter raised", exc))


def _detections(messages: Sequence[object]) -> list[Detection]:
    return [m for m in messages if isinstance(m, Detection)]


def _guard(number: int, evaluate: Callable[[], CheckResult]) -> CheckResult:
    try:
        return evaluate()
    except Exception as exc:  # an unexpected check failure fails that check only
        return CheckResult(
            number=number,
            name=CHECK_NAMES[number - 1],
            passed=False,
            reason=_describe("check raised", exc),
        )


def _blocked_by(number: int, outcomes: Sequence[_Outcome]) -> CheckResult | None:
    """A FAIL for ``number`` if any run it depends on raised, else None."""
    for outcome in outcomes:
        if outcome.error is not None:
            return CheckResult(
                number=number, name=CHECK_NAMES[number - 1], passed=False, reason=outcome.error
            )
    return None


def run_harness(
    adapter: SensorAdapter,
    sensor: SensorConfig,
    scenario: ScenarioConfig,
    real_raw: list[RawDetection],
) -> HarnessRun:
    """Run all seven checks against ``adapter`` and return the verdict and real Detections."""
    withheld = withheld_tick_indices(sensor, scenario)
    full_inputs = build_probe_stream(sensor, scenario)
    gap_inputs = build_probe_stream(sensor, scenario, withheld)

    real = _call(adapter, real_raw, sensor, scenario)
    full = _call(adapter, full_inputs, sensor, scenario)
    gap = _call(adapter, gap_inputs, sensor, scenario)
    all_runs = (real, full, gap)

    def over_all_runs(number: int, evaluate: Callable[[], CheckResult]) -> CheckResult:
        return _blocked_by(number, all_runs) or _guard(number, evaluate)

    def over_run(number: int, run: _Outcome, evaluate: Callable[[], CheckResult]) -> CheckResult:
        return _blocked_by(number, (run,)) or _guard(number, evaluate)

    def every_message() -> list[Detection | Heartbeat]:
        return [m for run in all_runs for m in run.messages]

    def every_detection() -> list[Detection]:
        return _detections(every_message())

    results = (
        over_all_runs(1, lambda: checks.check_schema(every_message())),
        over_all_runs(2, lambda: checks.check_units(every_detection(), sensor, scenario)),
        over_all_runs(
            3, lambda: checks.check_coordinate_frame(every_detection(), sensor, scenario)
        ),
        over_all_runs(
            4,
            lambda: checks.check_clock_offset(
                [
                    (real_raw, _detections(real.messages)),
                    (full_inputs, _detections(full.messages)),
                    (gap_inputs, _detections(gap.messages)),
                ],
                scenario,
            ),
        ),
        over_run(5, full, lambda: checks.check_update_rate(_detections(full.messages), sensor)),
        over_run(6, full, lambda: checks.check_heartbeat(full.messages, sensor, scenario)),
        over_run(
            7,
            gap,
            lambda: checks.check_dropped_messages(gap.messages, len(gap_inputs), len(withheld)),
        ),
    )
    return HarnessRun(
        result=HarnessResult(sensor_id=sensor.sensor_id, checks=results),
        real_detections=_detections(real.messages),
    )
