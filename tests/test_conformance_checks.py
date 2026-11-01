"""Probe and per-check tests for the conformance harness (specs/007-conformance-harness).

Each check is exercised directly with a passing and a failing fixture (SC-003).
Expected values are derived independently of the implementation under test.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.adapters.messages import Detection, Heartbeat
from src.config.loader import load_scenario_config, load_sensor_config
from src.conformance.checks import (
    check_clock_offset,
    check_coordinate_frame,
    check_dropped_messages,
    check_heartbeat,
    check_schema,
    check_units,
    check_update_rate,
)
from src.conformance.probes import (
    build_probe_stream,
    probe_position,
    sensor_position,
    withheld_tick_indices,
)
from src.conformance.results import CheckResult, HarnessResult
from src.simulator.detections import RawDetection, expected_ticks
from src.simulator.geo import distance_m

CONFIG_ROOT = Path(__file__).resolve().parent.parent / "config"
SENSOR = load_sensor_config(CONFIG_ROOT / "sensors" / "example_sensor.yaml")
SCENARIO = load_scenario_config(CONFIG_ROOT / "scenarios" / "example_scenario.yaml")
# A short schedule keeps hand-built message streams small: 2 Hz over 4 s = ticks 0, 0.5, ..., 4.0.
SHORT = SCENARIO.model_copy(update={"duration_s": 4.0})
CENTER = (SCENARIO.defended_area.center_lat, SCENARIO.defended_area.center_lon)


def _detection(index: int, t_s: float = 0.0, **overrides) -> Detection:
    fields = dict(
        sensor_id=SENSOR.sensor_id,
        detection_id=f"{SENSOR.sensor_id}:{index}:0",
        timestamp_utc=SCENARIO.start_utc + t_s,
        lat=CENTER[0],
        lon=CENTER[1],
        alt_m=100.0,
        accuracy_m=SENSOR.accuracy_m,
        raw_payload={},
    )
    fields.update(overrides)
    return Detection(**fields)


def _heartbeat(t_s: float, offset_s: float = 0.0) -> Heartbeat:
    return Heartbeat(
        sensor_id=SENSOR.sensor_id, timestamp_utc=SCENARIO.start_utc + t_s + offset_s, t_s=t_s
    )


def _stream(indices, offset_s: float = 0.0) -> list[Detection | Heartbeat]:
    """One message per listed tick of the SHORT schedule (Detections on even ticks)."""
    ticks = expected_ticks(SENSOR.update_rate_hz, SHORT.duration_s)
    return [
        _detection(i, ticks[i], timestamp_utc=SCENARIO.start_utc + ticks[i] + offset_s)
        if i % 2 == 0
        else _heartbeat(ticks[i], offset_s)
        for i in indices
    ]


def _raw(t_s: float) -> RawDetection:
    return RawDetection(
        sensor_id=SENSOR.sensor_id,
        t_s=t_s,
        lat=CENTER[0],
        lon=CENTER[1],
        alt_m=100.0,
        accuracy_m=SENSOR.accuracy_m,
    )


# --- Result types -----------------------------------------------------------


@pytest.mark.parametrize("reason", ["", "   ", "two\nlines"])
def test_check_result_rejects_empty_or_multiline_reason(reason):
    with pytest.raises(ValidationError, match="reason"):
        CheckResult(number=1, name="schema", passed=True, reason=reason)


def test_check_result_rejects_name_that_does_not_match_number():
    with pytest.raises(ValidationError, match="must be named 'schema'"):
        CheckResult(number=1, name="units", passed=True, reason="ok")


def _results(numbers):
    return tuple(
        CheckResult(
            number=n,
            name=("schema units coordinate_frame clock_offset update_rate heartbeat "
                  "dropped_messages").split()[n - 1],
            passed=True,
            reason="ok",
        )
        for n in numbers
    )


def test_harness_result_requires_exactly_seven_ordered_checks():
    assert HarnessResult(sensor_id="s", checks=_results(range(1, 8))).admitted
    with pytest.raises(ValidationError, match="numbered 1-7"):
        HarnessResult(sensor_id="s", checks=_results(range(1, 7)))
    with pytest.raises(ValidationError, match="numbered 1-7"):
        HarnessResult(sensor_id="s", checks=_results([2, 1, 3, 4, 5, 6, 7]))


def test_harness_result_is_admitted_only_if_every_check_passed():
    checks = list(_results(range(1, 8)))
    checks[3] = checks[3].model_copy(update={"passed": False})
    assert not HarnessResult(sensor_id="s", checks=tuple(checks)).admitted


# --- Probes (T014/T015) -----------------------------------------------------


@pytest.mark.parametrize("config", ["example_sensor.yaml", "sensor_2.yaml"])
def test_probe_position_round_trips_to_half_range(config):
    sensor = load_sensor_config(CONFIG_ROOT / "sensors" / config)
    lat, lon, alt_m = probe_position(sensor, SCENARIO)
    base = sensor_position(sensor, SCENARIO)
    assert distance_m(*base, lat, lon) == pytest.approx(sensor.range_m / 2, rel=1e-6)
    # Due east: same latitude as the sensor.
    assert lat == pytest.approx(base[0], abs=1e-9)
    assert lon > base[1]
    assert alt_m == (SCENARIO.min_alt_m + SCENARIO.max_alt_m) / 2


def test_probe_is_inside_check_2_and_3_bounds():
    lat, lon, alt_m = probe_position(SENSOR, SCENARIO)
    assert SCENARIO.min_alt_m <= alt_m <= SCENARIO.max_alt_m
    assert distance_m(*sensor_position(SENSOR, SCENARIO), lat, lon) <= (
        SENSOR.range_m + 6 * SENSOR.accuracy_m
    )


def test_full_probe_has_one_input_per_scheduled_tick():
    probe = build_probe_stream(SENSOR, SCENARIO)
    ticks = expected_ticks(SENSOR.update_rate_hz, SCENARIO.duration_s)
    assert [r.t_s for r in probe] == ticks
    assert {r.sensor_id for r in probe} == {SENSOR.sensor_id}


def test_gap_run_is_contiguous_and_longer_than_heartbeat_timeout():
    withheld = withheld_tick_indices(SENSOR, SCENARIO)
    ordered = sorted(withheld)
    assert ordered == list(range(ordered[0], ordered[0] + len(ordered)))
    # 2 Hz sensor, 1.0 s heartbeat timeout: the run must silence the sensor for more than 1.0 s.
    assert len(withheld) / SENSOR.update_rate_hz > SENSOR.heartbeat_timeout_s
    gap = build_probe_stream(SENSOR, SCENARIO, withheld)
    assert len(gap) == len(expected_ticks(SENSOR.update_rate_hz, SCENARIO.duration_s)) - len(
        withheld
    )


def test_gap_run_is_clamped_to_leave_inputs_before_and_after():
    # 2 Hz over 1.5 s = 4 ticks (0..3): the 4-tick run shrinks to keep ticks 0 and 3 supplied.
    scenario = SCENARIO.model_copy(update={"duration_s": 1.5})
    withheld = withheld_tick_indices(SENSOR, scenario)
    n_ticks = len(expected_ticks(SENSOR.update_rate_hz, scenario.duration_s))
    assert n_ticks == 4
    assert withheld and 0 not in withheld and (n_ticks - 1) not in withheld
    # A single-interval schedule leaves nothing to withhold.
    tiny = SCENARIO.model_copy(update={"duration_s": 0.5})
    assert withheld_tick_indices(SENSOR, tiny) == frozenset()


def test_probe_builds_are_identical():
    withheld = withheld_tick_indices(SENSOR, SCENARIO)
    a = build_probe_stream(SENSOR, SCENARIO, withheld)
    b = build_probe_stream(SENSOR, SCENARIO, withheld)
    assert [r.model_dump_json() for r in a] == [r.model_dump_json() for r in b]


# --- Check 1: schema --------------------------------------------------------


def test_schema_passes_valid_messages():
    result = check_schema([_detection(0), _heartbeat(0.5)])
    assert result.passed and result.number == 1 and result.name == "schema"


def test_schema_fails_unvalidated_out_of_range_confidence():
    bad = _detection(7).model_copy(update={"confidence": 1.5})  # skips validation
    result = check_schema([_detection(0), bad])
    assert not result.passed
    assert "message 1" in result.reason
    assert bad.detection_id in result.reason
    assert "confidence" in result.reason


def test_schema_fails_non_model_message():
    result = check_schema([_detection(0), {"lat": 1.0}])
    assert not result.passed
    assert "message 1" in result.reason and "dict" in result.reason


def test_schema_fails_when_there_are_no_detections():
    assert check_schema([_heartbeat(0.0)]).reason == "no Detections to evaluate"
    assert not check_schema([]).passed


# --- Check 2: units ---------------------------------------------------------


def test_units_pass_and_boundaries_are_inclusive():
    on_bounds = [
        _detection(0, alt_m=SCENARIO.min_alt_m, accuracy_m=SENSOR.max_accuracy_m),
        _detection(1, alt_m=SCENARIO.max_alt_m),
    ]
    assert check_units(on_bounds, SENSOR, SCENARIO).passed


def test_units_fail_when_drone_altitude_is_reported_in_feet():
    feet = _detection(3, alt_m=120.0 * 3.28084)  # 393.7 ft
    result = check_units([_detection(0), feet], SENSOR, SCENARIO)
    assert not result.passed
    assert feet.detection_id in result.reason
    assert "393.701" in result.reason and "200" in result.reason


def test_units_fail_on_implausible_accuracy():
    result = check_units([_detection(0, accuracy_m=60.0)], SENSOR, SCENARIO)
    assert not result.passed
    assert "accuracy_m 60" in result.reason and "50" in result.reason


def test_units_fail_with_no_detections():
    assert check_units([], SENSOR, SCENARIO).reason == "no Detections to evaluate"


# --- Check 3: coordinate frame ---------------------------------------------


def test_coordinate_frame_known_answer_one_degree_of_latitude():
    """One degree of latitude is 111,195 m: pi/180 x R1, R1 = 6,371.0 km (IUGG mean Earth radius).

    The bound is ``range_m + 6 x accuracy_m``, so a Detection 1 degree north of the
    sensor fails at range_m=100,000 and passes at range_m=111,200 (accuracy_m=1).
    """
    sensor = SENSOR.model_copy(update={"lat": 0.0, "lon": 0.0, "accuracy_m": 1.0})
    one_degree_north = _detection(0, lat=1.0, lon=0.0)
    near = check_coordinate_frame(
        [one_degree_north], sensor.model_copy(update={"range_m": 100_000.0}), SCENARIO
    )
    assert not near.passed and "111195 m" in near.reason
    far = check_coordinate_frame(
        [one_degree_north], sensor.model_copy(update={"range_m": 111_200.0}), SCENARIO
    )
    assert far.passed


def test_coordinate_frame_passes_for_the_probe_position():
    lat, lon, alt_m = probe_position(SENSOR, SCENARIO)
    assert check_coordinate_frame([_detection(0, lat=lat, lon=lon)], SENSOR, SCENARIO).passed


@pytest.mark.parametrize(
    "lat, lon",
    [
        (CENTER[1], CENTER[0]),
        (CENTER[0], -CENTER[1]),
        (math.radians(CENTER[0]), math.radians(CENTER[1])),
    ],
    ids=["swapped", "sign-flipped-lon", "radians"],
)
def test_coordinate_frame_fails_gross_frame_errors(lat, lon):
    result = check_coordinate_frame([_detection(0, lat=lat, lon=lon)], SENSOR, SCENARIO)
    assert not result.passed and "coverage bound" in result.reason


def test_coordinate_frame_fails_with_no_detections():
    assert check_coordinate_frame([], SENSOR, SCENARIO).reason == "no Detections to evaluate"


# --- Check 4: clock offset --------------------------------------------------

T_S = [0.0, 0.5, 1.0]


def _run(offset_s: float = 0.0, t_s=T_S):
    raws = [_raw(t) for t in t_s]
    dets = [
        _detection(i, t, timestamp_utc=SCENARIO.start_utc + t + offset_s)
        for i, t in enumerate(t_s)
    ]
    return raws, dets


def test_clock_offset_passes_with_no_offset():
    assert check_clock_offset([_run()], SCENARIO).passed


def test_clock_offset_known_answer_two_seconds_ahead():
    assert SCENARIO.start_utc == 1_735_689_600
    result = check_clock_offset([_run(offset_s=2.0)], SCENARIO)
    assert not result.passed
    assert "2.000 s ahead" in result.reason and "0.5" in result.reason


def test_clock_offset_reports_behind():
    assert "2.000 s behind" in check_clock_offset([_run(offset_s=-2.0)], SCENARIO).reason


def test_clock_offset_equal_to_the_limit_passes_and_just_over_fails():
    assert check_clock_offset([_run(offset_s=0.5)], SCENARIO).passed
    assert not check_clock_offset([_run(offset_s=0.5 + 2**-10)], SCENARIO).passed


def test_clock_offset_fails_on_count_mismatch():
    raws, dets = _run()
    result = check_clock_offset([(raws, dets[:-1])], SCENARIO)
    assert not result.passed and "2 Detections for 3 inputs" in result.reason


def test_clock_offset_fails_if_any_run_is_bad():
    result = check_clock_offset([_run(), _run(offset_s=2.0)], SCENARIO)
    assert not result.passed and "ahead" in result.reason


def test_clock_offset_fails_with_no_pairs():
    assert check_clock_offset([], SCENARIO).reason == "no Detections to evaluate"
    assert not check_clock_offset([([], [])], SCENARIO).passed


# --- Check 5: update rate ---------------------------------------------------


def _timed(count: int, interval_s: float, offset_s: float = 0.0) -> list[Detection]:
    return [
        _detection(i, timestamp_utc=SCENARIO.start_utc + offset_s + i * interval_s)
        for i in range(count)
    ]


def test_update_rate_known_answer_eleven_detections_half_a_second_apart_is_2_hz():
    result = check_update_rate(_timed(11, 0.5), SENSOR)
    assert result.passed and "2.000 Hz" in result.reason


def test_update_rate_fails_at_half_rate():
    result = check_update_rate(_timed(11, 1.0), SENSOR)
    assert not result.passed and "1.000 Hz" in result.reason


def test_update_rate_bounds_are_inclusive():
    exact = SENSOR.model_copy(update={"min_hz": 2.0, "max_hz": 2.0})
    assert check_update_rate(_timed(11, 0.5), exact).passed


def test_update_rate_fails_with_fewer_than_two_detections():
    assert not check_update_rate(_timed(1, 0.5), SENSOR).passed
    assert not check_update_rate([], SENSOR).passed


def test_update_rate_is_invariant_to_a_constant_offset():
    assert check_update_rate(_timed(11, 0.5, offset_s=2.0), SENSOR) == check_update_rate(
        _timed(11, 0.5), SENSOR
    )


# --- Check 6: heartbeat -----------------------------------------------------

ALL_TICKS = range(9)  # SHORT: 9 scheduled ticks, span 4.0 s; heartbeat_timeout_s = 1.0


def test_heartbeat_passes_when_every_tick_is_accounted_for():
    assert check_heartbeat(_stream(ALL_TICKS), SENSOR, SHORT).passed


def test_heartbeat_fails_on_a_silent_mid_stream_run():
    result = check_heartbeat(_stream([0, 1, 2, 7, 8]), SENSOR, SHORT)
    assert not result.passed and "silent for 2.500 s" in result.reason


def test_heartbeat_fails_when_the_stream_stops_early():
    result = check_heartbeat(_stream(range(5)), SENSOR, SHORT)
    assert not result.passed and "less than the schedule" in result.reason


def test_heartbeat_gap_equal_to_the_timeout_passes():
    # Dropping tick 2 leaves exactly 1.0 s between ticks 1 and 3.
    assert check_heartbeat(_stream([0, 1, 3, 4, 5, 6, 7, 8]), SENSOR, SHORT).passed


def test_heartbeat_fails_on_an_empty_message_list():
    result = check_heartbeat([], SENSOR, SHORT)
    assert not result.passed and result.reason == "no messages to evaluate"


def test_heartbeat_is_invariant_to_a_constant_offset():
    good, bad = list(ALL_TICKS), [0, 1, 2, 7, 8]
    for indices in (good, bad):
        assert check_heartbeat(_stream(indices, offset_s=2.0), SENSOR, SHORT).passed == (
            check_heartbeat(_stream(indices), SENSOR, SHORT).passed
        )


# --- Check 7: dropped messages ---------------------------------------------


def _gap_messages(detections: int, heartbeats: int) -> list[Detection | Heartbeat]:
    return [_detection(i, i * 0.5) for i in range(detections)] + [
        _heartbeat(10.0 + i) for i in range(heartbeats)
    ]


def test_dropped_messages_passes_when_counts_match():
    assert check_dropped_messages(_gap_messages(3, 2), 3, 2).passed


def test_dropped_messages_fails_on_a_skipped_heartbeat():
    result = check_dropped_messages(_gap_messages(3, 1), 3, 2)
    assert not result.passed and "1 Heartbeats for 2 withheld ticks" in result.reason


def test_dropped_messages_fails_on_a_fabricated_detection():
    result = check_dropped_messages(_gap_messages(4, 2), 3, 2)
    assert not result.passed and "4 Detections for 3 inputs" in result.reason


def test_dropped_messages_fails_on_duplicate_detection_ids():
    messages = _gap_messages(3, 2)
    messages[1] = messages[0]
    result = check_dropped_messages(messages, 3, 2)
    assert not result.passed and "duplicate detection_id" in result.reason
