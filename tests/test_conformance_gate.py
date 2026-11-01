"""Gate tests: only admitted adapters' Detections reach a downstream consumer (FR-011)."""

from __future__ import annotations

import pytest

from src.adapters.base import translate
from src.conformance import checks
from src.conformance.gate import ConformanceGate
from tests.conformance_fixtures import (
    SCENARIO,
    SENSORS,
    StubFusion,
    offset_adapter,
    raising_adapter,
    real_streams,
)

SENSOR_1, SENSOR_2 = SENSORS


def _submit(gate, adapter, sensor):
    return gate.submit(adapter, sensor, SCENARIO, real_streams()[sensor.sensor_id])


def test_stub_fusion_only_receives_detections_from_admitted_sensors():
    gate = ConformanceGate()
    _submit(gate, translate, SENSOR_1)
    _submit(gate, offset_adapter, SENSOR_2)

    fusion = {sensor.sensor_id: StubFusion() for sensor in SENSORS}
    for sensor in SENSORS:
        fusion[sensor.sensor_id].ingest(gate.admitted_detections(sensor.sensor_id))

    assert len(fusion[SENSOR_1.sensor_id].received) > 0
    assert fusion[SENSOR_2.sensor_id].received == []
    assert [r.admitted for r in gate.results()] == [True, False]


def test_resubmitting_a_fixed_adapter_flips_blocked_to_admitted():
    gate = ConformanceGate()
    blocked = _submit(gate, offset_adapter, SENSOR_1)
    assert not blocked.admitted
    assert gate.admitted_detections(SENSOR_1.sensor_id) == []

    admitted = _submit(gate, translate, SENSOR_1)
    assert admitted.admitted
    assert len(gate.admitted_detections(SENSOR_1.sensor_id)) == len(
        real_streams()[SENSOR_1.sensor_id]
    )
    assert gate.results() == [admitted]


def test_resubmitting_a_broken_adapter_withdraws_an_earlier_admission():
    gate = ConformanceGate()
    _submit(gate, translate, SENSOR_1)
    _submit(gate, offset_adapter, SENSOR_1)
    assert gate.admitted_detections(SENSOR_1.sensor_id) == []


def test_results_keep_first_submission_order_per_sensor():
    gate = ConformanceGate()
    _submit(gate, translate, SENSOR_2)
    _submit(gate, translate, SENSOR_1)
    _submit(gate, offset_adapter, SENSOR_2)
    assert [r.sensor_id for r in gate.results()] == [SENSOR_2.sensor_id, SENSOR_1.sensor_id]


def test_an_adapter_that_raises_is_blocked_with_the_exception_named():
    gate = ConformanceGate()
    result = _submit(gate, raising_adapter, SENSOR_1)
    assert not result.admitted
    assert all(not c.passed for c in result.checks)
    assert all(c.reason == "adapter raised RuntimeError: boom" for c in result.checks)
    assert gate.admitted_detections(SENSOR_1.sensor_id) == []


def test_unknown_sensor_id_has_no_admitted_detections():
    assert ConformanceGate().admitted_detections("never-submitted") == []


def test_a_raising_check_fails_alone_and_the_other_six_still_report(monkeypatch):
    """FR-012: one check function raising must not stop or hide the other six."""

    def exploding_check(*args, **kwargs):
        raise RuntimeError("kaboom\ntraceback detail")

    monkeypatch.setattr(checks, "check_units", exploding_check)
    result = _submit(ConformanceGate(), translate, SENSOR_1)

    assert [c.number for c in result.checks] == [1, 2, 3, 4, 5, 6, 7]
    units = result.checks[1]
    assert not units.passed
    assert units.reason == "check raised RuntimeError: kaboom"
    assert [c.passed for c in result.checks if c.number != 2] == [True] * 6
    assert not result.admitted


@pytest.mark.parametrize("sensor", SENSORS, ids=lambda s: s.sensor_id)
def test_admitted_detections_returns_a_copy(sensor):
    gate = ConformanceGate()
    _submit(gate, translate, sensor)
    gate.admitted_detections(sensor.sensor_id).clear()
    assert gate.admitted_detections(sensor.sensor_id)
