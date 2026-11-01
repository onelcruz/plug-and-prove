"""Sensor 3 (#8): the demo adapter with an injected clock-offset bug, and its fix."""

from __future__ import annotations

from copy import deepcopy
from functools import cache

import pytest

from src.adapters import sensor1, sensor2, sensor3
from src.adapters.base import translate as base_translate
from src.adapters.messages import Detection, Heartbeat
from src.config.loader import load_scenario_config, load_sensor_config
from src.conformance.gate import ConformanceGate
from src.conformance.harness import run_harness
from src.conformance.report import render_markdown
from src.simulator.detections import RawDetection
from src.simulator.geo import distance_m
from src.simulator.scenario import run_simulation
from tests.conformance_fixtures import CONFIG_ROOT, SCENARIO, SENSORS, real_streams

SENSOR_1 = SENSORS[0]
SENSOR_3_CONFIG_PATH = CONFIG_ROOT / "sensors" / "sensor_3.yaml"
SENSOR_3 = sensor3.sensor_config


@cache
def _three_sensor_run():
    """The example scenario with sensor 3 appended after sensors 1 and 2 (FR-010)."""
    return run_simulation(SCENARIO, [*SENSORS, SENSOR_3])


def _sensor3_raw() -> list[RawDetection]:
    return _three_sensor_run().detections_by_sensor["sensor-3"]


def offset_exceeds_limit(offset_s: float, limit_s: float) -> bool:
    """Strictly greater: check 4's limit is inclusive, so an offset equal to it would pass."""
    return abs(offset_s) > limit_s


def assert_blocked_by_check4_only(result) -> None:
    failing = [check.number for check in result.checks if not check.passed]
    assert not result.admitted, "expected BLOCKED, got ADMITTED"
    assert failing == [4], f"expected only check 4 to fail, got {failing}"


def assert_scenario_unmodified(scenario) -> None:
    fresh = load_scenario_config(CONFIG_ROOT / "scenarios" / "example_scenario.yaml")
    assert scenario.model_dump() == fresh.model_dump(), "scenario differs from the example file"


def _shift(messages, offset_s, detections_only=False):
    return [
        m.model_copy(update={"timestamp_utc": m.timestamp_utc + offset_s})
        if (isinstance(m, Detection) or not detections_only)
        else m
        for m in messages
    ]


def detections_only_offset_adapter(raw, sensor, scenario):
    """A faulty adapter: +18 s on Detections but not Heartbeats (also fails check 7)."""
    return _shift(base_translate(raw, sensor, scenario), 18.0, detections_only=True)


def limit_offset_adapter(raw, sensor, scenario):
    """A faulty-looking adapter whose offset equals the (inclusive) limit exactly."""
    return _shift(base_translate(raw, sensor, scenario), scenario.max_clock_offset_s)


def _run(adapter, sensor=SENSOR_1, scenario=SCENARIO):
    return run_harness(adapter, sensor, scenario, real_streams()[sensor.sensor_id]).result


def test_sensor3_config_matches_the_plan():
    config = load_sensor_config(SENSOR_3_CONFIG_PATH)
    assert (config.sensor_id, config.accuracy_m, config.range_m) == ("sensor-3", 5.0, 2500)
    assert (config.update_rate_hz, config.dropout_probability) == (1.0, 0.03)
    assert (config.heartbeat_timeout_s, config.lat, config.lon) == (2.0, 38.8960, -77.0280)
    assert (config.min_hz, config.max_hz, config.max_accuracy_m) == (0.5, 1.5, 50.0)


def test_sensor3_config_is_distinct_and_has_no_offset_field():
    config = load_sensor_config(SENSOR_3_CONFIG_PATH)
    assert config.sensor_id not in {"sensor-1", "sensor-2", "sensor-3-test"}
    assert not [name for name in type(config).model_fields if "offset" in name]


def test_offset_exceeds_limit_rejects_an_offset_equal_to_the_limit():
    assert offset_exceeds_limit(0.5, 0.5) is False
    assert offset_exceeds_limit(0.5000001, 0.5) is True
    assert offset_exceeds_limit(18.0, 0.5) is True


def test_a_clean_adapter_is_not_blocked_by_check_4_only():
    with pytest.raises(AssertionError):
        assert_blocked_by_check4_only(_run(base_translate))


def test_a_detections_only_offset_is_not_blocked_by_check_4_only():
    # Sneakiest input: it fails check 4, but check 7 fails too.
    result = _run(detections_only_offset_adapter)
    assert not result.admitted
    with pytest.raises(AssertionError):
        assert_blocked_by_check4_only(result)


def test_an_offset_equal_to_the_limit_is_admitted():
    # Sneakiest input for the demo bug: the limit is inclusive, so this does not fail check 4.
    assert _run(limit_offset_adapter).admitted


def test_a_loosened_limit_is_not_an_unmodified_scenario():
    loosened = SCENARIO.model_copy(update={"max_clock_offset_s": 20.0})
    with pytest.raises(AssertionError):
        assert_scenario_unmodified(loosened)
    assert_scenario_unmodified(SCENARIO)


def test_gps_utc_offset_is_eighteen_seconds_and_exceeds_the_scenario_limit():
    """GPS - UTC = 18 s since 2017-01-01 (IERS Bulletin C 52)."""
    fresh = load_scenario_config(CONFIG_ROOT / "scenarios" / "example_scenario.yaml")
    assert sensor3.GPS_UTC_OFFSET_S == 18.0
    assert offset_exceeds_limit(sensor3.GPS_UTC_OFFSET_S, fresh.max_clock_offset_s)


def test_buggy_timestamp_of_the_first_tick_is_eighteen_seconds_past_epoch_reference():
    """start_utc 1735689600 is 2025-01-01T00:00:00Z (external epoch converter)."""
    point = {"lat": 38.896, "lon": -77.028, "alt_m": 50.0, "accuracy_m": 5.0}
    raw = [RawDetection(sensor_id="sensor-3", t_s=0.0, **point)]
    first = sensor3.translate_with_clock_bug(raw, SENSOR_3, SCENARIO)[0]
    assert first.timestamp_utc == 1_735_689_618.0  # 2025-01-01T00:00:18Z


def test_buggy_adapter_shifts_only_timestamps_by_the_offset_on_every_message():
    # Sensor 3's real stream has a Detection on every tick, so truncate it: ticks after 60 s become
    # Heartbeats, and the shift must reach those too (otherwise check 7 fails as well).
    raw = [r for r in _sensor3_raw() if r.t_s < 60.0]
    reference = base_translate(raw, SENSOR_3, SCENARIO)
    buggy = sensor3.translate_with_clock_bug(raw, SENSOR_3, SCENARIO)
    assert len(buggy) == len(reference)
    assert any(isinstance(m, Heartbeat) for m in reference)
    assert any(isinstance(m, Detection) for m in reference)
    for got, want in zip(buggy, reference, strict=True):
        assert type(got) is type(want)
        assert got.timestamp_utc == want.timestamp_utc + sensor3.GPS_UTC_OFFSET_S
        assert got.model_copy(update={"timestamp_utc": want.timestamp_utc}) == want


def test_buggy_adapter_does_not_mutate_its_inputs():
    raw = _sensor3_raw()
    before = deepcopy(raw)
    sensor_before, scenario_before = SENSOR_3.model_copy(), SCENARIO.model_copy()
    sensor3.translate_with_clock_bug(raw, SENSOR_3, SCENARIO)
    assert raw == before
    assert (SENSOR_3, SCENARIO) == (sensor_before, scenario_before)


def test_buggy_adapter_is_blocked_by_check_4_only_with_an_explanatory_reason():
    gate = ConformanceGate()
    result = gate.submit(sensor3.translate_with_clock_bug, SENSOR_3, SCENARIO, _sensor3_raw())
    assert_blocked_by_check4_only(result)
    reason = result.checks[3].reason
    assert reason == "timestamp_utc is 18.000 s ahead, limit is 0.5 s"
    assert gate.admitted_detections("sensor-3") == []
    report = render_markdown(gate.results())
    assert "sensor-3" in report and "BLOCKED" in report and reason in report
    assert_scenario_unmodified(SCENARIO)


def test_fixed_adapter_output_equals_the_shared_translation_exactly():
    raw = _sensor3_raw()
    assert sensor3.translate is not base_translate
    assert sensor3.translate(raw, SENSOR_3, SCENARIO) == base_translate(raw, SENSOR_3, SCENARIO)


def test_fixed_adapter_is_admitted_on_all_seven_checks_with_the_unmodified_scenario():
    raw = _sensor3_raw()
    gate = ConformanceGate()
    result = gate.submit(sensor3.translate, SENSOR_3, SCENARIO, raw)
    assert result.admitted
    assert [check.number for check in result.checks if check.passed] == [1, 2, 3, 4, 5, 6, 7]
    released = gate.admitted_detections("sensor-3")
    assert len(released) == len(raw)
    assert sorted(d.timestamp_utc for d in released) == sorted(
        SCENARIO.start_utc + r.t_s for r in raw
    )
    assert_scenario_unmodified(SCENARIO)


def double_subtract_adapter(raw, sensor, scenario):
    """A faulty "fix" that over-corrects: converts GPS to UTC, then subtracts the offset again."""
    return _shift(sensor3.translate(raw, sensor, scenario), -sensor3.GPS_UTC_OFFSET_S)


def test_fail_fix_pass_on_one_gate():
    gate = ConformanceGate()
    streams = _three_sensor_run().detections_by_sensor
    gate.submit(sensor1.translate, SENSORS[0], SCENARIO, streams["sensor-1"])
    gate.submit(sensor2.translate, SENSORS[1], SCENARIO, streams["sensor-2"])
    others_before = list(gate.results())

    blocked = gate.submit(sensor3.translate_with_clock_bug, SENSOR_3, SCENARIO, streams["sensor-3"])
    assert_blocked_by_check4_only(blocked)
    assert gate.admitted_detections("sensor-3") == []

    fixed = gate.submit(sensor3.translate, SENSOR_3, SCENARIO, streams["sensor-3"])
    assert fixed.admitted

    results = gate.results()
    assert [r.sensor_id for r in results] == ["sensor-1", "sensor-2", "sensor-3"]
    assert results[:2] == others_before
    assert results[2].admitted and results[2] == fixed
    assert len(gate.admitted_detections("sensor-3")) == len(streams["sensor-3"])
    assert_scenario_unmodified(SCENARIO)


def test_an_over_correcting_fix_stays_blocked_by_check_4():
    # Sneakiest "fix": the verdict changes reason ("behind"), but the sensor is still not admitted.
    gate = ConformanceGate()
    raw = _sensor3_raw()
    gate.submit(sensor3.translate_with_clock_bug, SENSOR_3, SCENARIO, raw)
    result = gate.submit(double_subtract_adapter, SENSOR_3, SCENARIO, raw)
    assert_blocked_by_check4_only(result)
    assert "18.000 s behind" in result.checks[3].reason
    assert gate.admitted_detections("sensor-3") == []


def test_adding_sensor_3_leaves_sensors_1_and_2_streams_unchanged():
    streams = _three_sensor_run().detections_by_sensor
    for sensor in SENSORS:
        assert streams[sensor.sensor_id] == real_streams()[sensor.sensor_id]


def test_sensor3_sees_the_drone():
    run = _three_sensor_run()
    drones = [o for o in run.truth_objects if o.kind == "drone"]
    near_a_drone = [
        raw
        for raw in _sensor3_raw()
        for drone in drones
        if (p := drone.position_at(raw.t_s)) is not None
        and distance_m(raw.lat, raw.lon, p.lat, p.lon) <= 3 * SENSOR_3.accuracy_m
    ]
    assert near_a_drone, "sensor 3 produced no drone detections"


@pytest.mark.parametrize(
    "start_utc",
    [
        1_073_741_823.9999999,  # just below 2**30: adding 18 s crosses a float64 binade
        2_147_483_630.0,  # 18 s before 2**31 (the year-2038 boundary)
    ],
)
def test_fixed_adapter_is_exact_at_float_binade_boundaries(start_utc):
    scenario = SCENARIO.model_copy(update={"start_utc": start_utc, "max_clock_offset_s": 1e-8})
    raw = _sensor3_raw()
    assert sensor3.translate(raw, SENSOR_3, scenario) == base_translate(raw, SENSOR_3, scenario)
    assert run_harness(sensor3.translate, SENSOR_3, scenario, raw).result.admitted
