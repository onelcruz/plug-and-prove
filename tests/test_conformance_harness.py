"""End-to-end harness tests: known-good adapters are admitted, faulty ones fail only their check."""

from __future__ import annotations

import time

import pytest

from src.adapters.base import translate
from src.adapters.messages import Detection
from src.conformance.gate import ConformanceGate
from src.conformance.harness import run_harness
from src.simulator.scenario import run_simulation
from tests.conformance_fixtures import (
    SCENARIO,
    SENSORS,
    duplicate_id_adapter,
    feet_adapter,
    heartbeat_dropping_adapter,
    mutating_input_adapter,
    mutating_limit_adapter,
    offset_adapter,
    real_streams,
    replayed_heartbeat_adapter,
    wrong_sensor_id_adapter,
)

SENSOR_1 = SENSORS[0]


def _failed_numbers(result) -> list[int]:
    return [c.number for c in result.checks if not c.passed]


def test_known_good_adapters_are_admitted_within_the_time_budget():
    """SC-001/SC-005: both adapters pass all 7 checks; simulation plus gate takes < 60 s."""
    started = time.perf_counter()
    streams = run_simulation(SCENARIO, list(SENSORS)).detections_by_sensor
    gate = ConformanceGate()
    results = [
        gate.submit(translate, sensor, SCENARIO, streams[sensor.sensor_id]) for sensor in SENSORS
    ]
    elapsed_s = time.perf_counter() - started

    assert elapsed_s < 60.0
    for sensor, result in zip(SENSORS, results, strict=True):
        assert result.sensor_id == sensor.sensor_id
        assert [c.number for c in result.checks] == [1, 2, 3, 4, 5, 6, 7]
        assert all(c.passed for c in result.checks), [c.reason for c in result.checks]
        assert result.admitted
        released = gate.admitted_detections(sensor.sensor_id)
        assert released and all(isinstance(d, Detection) for d in released)
        assert len(released) == len(streams[sensor.sensor_id])


def test_clock_offset_adapter_fails_only_check_4():
    """SC-002: a +2.0 s skew is blocked by check 4, with the measured offset in the reason."""
    run = run_harness(offset_adapter, SENSOR_1, SCENARIO, real_streams()[SENSOR_1.sensor_id])
    assert _failed_numbers(run.result) == [4]
    assert not run.result.admitted
    check_4 = run.result.checks[3]
    assert "2.000 s ahead" in check_4.reason and "0.5" in check_4.reason


def test_altitude_in_feet_fails_only_check_2():
    run = run_harness(feet_adapter, SENSOR_1, SCENARIO, real_streams()[SENSOR_1.sensor_id])
    assert _failed_numbers(run.result) == [2]
    assert "alt_m" in run.result.checks[1].reason


def test_dropping_heartbeats_fails_only_check_7():
    run = run_harness(
        heartbeat_dropping_adapter, SENSOR_1, SCENARIO, real_streams()[SENSOR_1.sensor_id]
    )
    assert _failed_numbers(run.result) == [7]
    assert "Heartbeats for" in run.result.checks[6].reason


def test_run_harness_returns_only_real_stream_detections():
    real_raw = real_streams()[SENSOR_1.sensor_id]
    run = run_harness(translate, SENSOR_1, SCENARIO, real_raw)
    assert run.real_detections == [
        m for m in translate(real_raw, SENSOR_1, SCENARIO) if isinstance(m, Detection)
    ]


@pytest.mark.parametrize("sensor", SENSORS, ids=lambda s: s.sensor_id)
def test_real_detections_are_not_mutated_by_the_harness(sensor):
    real_raw = real_streams()[sensor.sensor_id]
    before = [r.model_dump_json() for r in real_raw]
    run_harness(translate, sensor, SCENARIO, real_raw)
    assert [r.model_dump_json() for r in real_raw] == before


# --- PR #28 review findings: each fixture was ADMITTED before the fix ------


@pytest.mark.parametrize("sensor", SENSORS, ids=lambda s: s.sensor_id)
def test_adapter_emitting_another_sensor_id_is_blocked_by_check_1(sensor):
    run = run_harness(wrong_sensor_id_adapter, sensor, SCENARIO, real_streams()[sensor.sensor_id])
    assert _failed_numbers(run.result) == [1]
    assert "sensor-other" in run.result.checks[0].reason
    assert sensor.sensor_id in run.result.checks[0].reason


@pytest.mark.parametrize("sensor", SENSORS, ids=lambda s: s.sensor_id)
def test_duplicate_detection_ids_in_the_real_stream_are_blocked_by_check_1(sensor):
    run = run_harness(duplicate_id_adapter, sensor, SCENARIO, real_streams()[sensor.sensor_id])
    assert _failed_numbers(run.result) == [1]
    assert "duplicate detection_id" in run.result.checks[0].reason


@pytest.mark.parametrize("sensor", SENSORS, ids=lambda s: s.sensor_id)
def test_one_heartbeat_replayed_for_every_withheld_tick_is_blocked_by_check_7(sensor):
    run = run_harness(
        replayed_heartbeat_adapter, sensor, SCENARIO, real_streams()[sensor.sensor_id]
    )
    assert _failed_numbers(run.result) == [7]
    assert "Heartbeat" in run.result.checks[6].reason


def test_adapter_cannot_loosen_the_acceptance_limit_it_is_judged_by():
    scenario = SCENARIO.model_copy(deep=True)
    run = run_harness(
        mutating_limit_adapter, SENSOR_1, scenario, real_streams()[SENSOR_1.sensor_id]
    )
    assert scenario.max_clock_offset_s == SCENARIO.max_clock_offset_s
    assert _failed_numbers(run.result) == [4]


def test_adapter_cannot_change_the_harness_reference_times_or_callers_stream():
    real_raw = [r.model_copy() for r in real_streams()[SENSOR_1.sensor_id]]
    before = [r.model_dump_json() for r in real_raw]
    run = run_harness(mutating_input_adapter, SENSOR_1, SCENARIO, real_raw)
    assert [r.model_dump_json() for r in real_raw] == before
    assert _failed_numbers(run.result) == [4]
