"""The seven adapter contract checks (architecture.md §4, specs/007-conformance-harness).

Each check is a pure function over evidence that returns exactly one
``CheckResult`` with a single-line, fault-specific reason. Checks never raise
because of bad adapter output; the harness additionally wraps each call so an
unexpected exception fails only that check (FR-012). Checks 5-7 depend only on
intervals and counts, so a constant ``timestamp_utc`` offset does not change them
(FR-009a) -- that fault is isolated to check 4.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import ValidationError

from src.adapters.messages import Detection, Heartbeat
from src.config.models import ScenarioConfig, SensorConfig
from src.conformance.probes import sensor_position
from src.conformance.results import CHECK_NAMES, CheckResult
from src.simulator.detections import RawDetection, expected_ticks
from src.simulator.geo import distance_m

_NO_DETECTIONS = "no Detections to evaluate"


def _result(number: int, passed: bool, reason: str) -> CheckResult:
    return CheckResult(number=number, name=CHECK_NAMES[number - 1], passed=passed, reason=reason)


def _pass(number: int, reason: str) -> CheckResult:
    return _result(number, True, reason)


def _fail(number: int, reason: str) -> CheckResult:
    return _result(number, False, reason)


def check_schema(messages: Sequence[object]) -> CheckResult:
    """Check 1: every message is a valid ``Detection`` or ``Heartbeat``.

    Instances are re-validated from their dump, which catches objects built with
    ``model_construct``/``model_copy(update=...)`` that skipped validation.
    """
    detection_count = 0
    for index, message in enumerate(messages):
        if not isinstance(message, Detection | Heartbeat):
            return _fail(
                1,
                f"message {index} is not a Detection or Heartbeat (got {type(message).__name__})",
            )
        try:
            type(message).model_validate(message.model_dump())
        except ValidationError as exc:
            error = exc.errors()[0]
            field = ".".join(str(part) for part in error["loc"]) or "<model>"
            detection_id = getattr(message, "detection_id", None)
            who = f"message {index}" + (f" ({detection_id})" if detection_id else "")
            return _fail(1, f"{who} field {field}: {error['msg']}")
        if isinstance(message, Detection):
            detection_count += 1
    if detection_count == 0:
        return _fail(1, _NO_DETECTIONS)
    return _pass(1, f"{len(messages)} messages valid ({detection_count} Detections)")


def check_units(
    detections: Sequence[Detection], sensor: SensorConfig, scenario: ScenarioConfig
) -> CheckResult:
    """Check 2: ``alt_m`` and ``accuracy_m`` are plausible meters (bounds inclusive)."""
    if not detections:
        return _fail(2, _NO_DETECTIONS)
    violations: list[str] = []
    for det in detections:
        if not scenario.min_alt_m <= det.alt_m <= scenario.max_alt_m:
            violations.append(
                f"{det.detection_id} alt_m {det.alt_m:g} is outside "
                f"[{scenario.min_alt_m:g}, {scenario.max_alt_m:g}] m"
            )
        if det.accuracy_m > sensor.max_accuracy_m:
            violations.append(
                f"{det.detection_id} accuracy_m {det.accuracy_m:g} exceeds "
                f"max_accuracy_m {sensor.max_accuracy_m:g}"
            )
    if violations:
        more = f" (+{len(violations) - 1} more)" if len(violations) > 1 else ""
        return _fail(2, violations[0] + more)
    return _pass(2, f"{len(detections)} Detections within unit bounds")


def check_coordinate_frame(
    detections: Sequence[Detection], sensor: SensorConfig, scenario: ScenarioConfig
) -> CheckResult:
    """Check 3: every ``Detection`` lies within ``range_m + 6 x accuracy_m`` of the sensor."""
    if not detections:
        return _fail(3, _NO_DETECTIONS)
    base_lat, base_lon = sensor_position(sensor, scenario)
    bound_m = sensor.range_m + 6.0 * sensor.accuracy_m
    for det in detections:
        dist_m = distance_m(base_lat, base_lon, det.lat, det.lon)
        if dist_m > bound_m:
            return _fail(
                3,
                f"{det.detection_id} is {dist_m:.0f} m from the sensor, beyond the "
                f"{bound_m:.0f} m coverage bound",
            )
    return _pass(3, f"{len(detections)} Detections within {bound_m:.0f} m of the sensor")


def check_clock_offset(
    runs: Sequence[tuple[Sequence[RawDetection], Sequence[Detection]]],
    scenario: ScenarioConfig,
) -> CheckResult:
    """Check 4: ``timestamp_utc`` matches the harness-side reference ``start_utc + t_s``.

    Each run pairs the raw inputs the harness supplied with the Detections the
    adapter returned for them; sorted references are compared with sorted output
    timestamps (research.md R2).
    """
    limit_s = scenario.max_clock_offset_s
    pairs = 0
    worst_s = 0.0
    for run_index, (raw_inputs, detections) in enumerate(runs, start=1):
        if len(raw_inputs) != len(detections):
            return _fail(
                4,
                f"run {run_index}: {len(detections)} Detections for {len(raw_inputs)} "
                "inputs supplied",
            )
        references = sorted(scenario.start_utc + raw.t_s for raw in raw_inputs)
        timestamps = sorted(det.timestamp_utc for det in detections)
        for reference, timestamp in zip(references, timestamps, strict=True):
            pairs += 1
            diff_s = timestamp - reference
            if abs(diff_s) > abs(worst_s):
                worst_s = diff_s
    if pairs == 0:
        return _fail(4, _NO_DETECTIONS)
    if abs(worst_s) > limit_s:
        direction = "ahead" if worst_s > 0 else "behind"
        return _fail(
            4, f"timestamp_utc is {abs(worst_s):.3f} s {direction}, limit is {limit_s:g} s"
        )
    return _pass(4, f"worst offset {abs(worst_s):.3f} s within {limit_s:g} s ({pairs} Detections)")


def check_update_rate(
    full_probe_detections: Sequence[Detection], sensor: SensorConfig
) -> CheckResult:
    """Check 5: the measured ``Detection`` rate lies within ``[min_hz, max_hz]``."""
    timestamps = sorted(det.timestamp_utc for det in full_probe_detections)
    if len(timestamps) < 2:
        return _fail(5, f"need at least 2 Detections to measure a rate, got {len(timestamps)}")
    span_s = timestamps[-1] - timestamps[0]
    if span_s <= 0:
        return _fail(5, "Detections share one timestamp; no rate can be measured")
    rate_hz = (len(timestamps) - 1) / span_s
    if not sensor.min_hz <= rate_hz <= sensor.max_hz:
        return _fail(
            5,
            f"measured rate {rate_hz:.3f} Hz is outside [{sensor.min_hz:g}, {sensor.max_hz:g}] Hz",
        )
    return _pass(
        5, f"measured rate {rate_hz:.3f} Hz within [{sensor.min_hz:g}, {sensor.max_hz:g}] Hz"
    )


def check_heartbeat(
    full_probe_messages: Sequence[Detection | Heartbeat],
    sensor: SensorConfig,
    scenario: ScenarioConfig,
) -> CheckResult:
    """Check 6: no silence longer than ``heartbeat_timeout_s`` between or after messages."""
    if not full_probe_messages:
        return _fail(6, "no messages to evaluate")
    timeout_s = sensor.heartbeat_timeout_s
    timestamps = sorted(m.timestamp_utc for m in full_probe_messages)
    for earlier, later in zip(timestamps, timestamps[1:], strict=False):
        if later - earlier > timeout_s:
            return _fail(
                6, f"silent for {later - earlier:.3f} s between messages, limit is {timeout_s:g} s"
            )
    ticks = expected_ticks(sensor.update_rate_hz, scenario.duration_s)
    shortfall_s = (ticks[-1] - ticks[0]) - (timestamps[-1] - timestamps[0])
    if shortfall_s > timeout_s:
        return _fail(
            6,
            f"stream covers {shortfall_s:.3f} s less than the schedule, limit is {timeout_s:g} s",
        )
    return _pass(6, f"no silence longer than {timeout_s:g} s across {len(timestamps)} messages")


def check_dropped_messages(
    gap_probe_messages: Sequence[Detection | Heartbeat],
    supplied_count: int,
    withheld_count: int,
) -> CheckResult:
    """Check 7: a gap in the input yields one Heartbeat per withheld tick and nothing invented."""
    detections = [m for m in gap_probe_messages if isinstance(m, Detection)]
    heartbeat_count = sum(1 for m in gap_probe_messages if isinstance(m, Heartbeat))
    problems: list[str] = []
    if len(detections) != supplied_count:
        problems.append(f"{len(detections)} Detections for {supplied_count} inputs supplied")
    if heartbeat_count != withheld_count:
        problems.append(f"{heartbeat_count} Heartbeats for {withheld_count} withheld ticks")
    ids = [d.detection_id for d in detections]
    if len(set(ids)) != len(ids):
        problems.append("duplicate detection_id values")
    if problems:
        return _fail(7, "; ".join(problems))
    return _pass(
        7, f"{len(detections)} Detections and {heartbeat_count} Heartbeats match the gap probe"
    )
