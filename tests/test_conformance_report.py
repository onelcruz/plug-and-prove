"""Report tests (SC-006): one non-empty reason line per check, deterministic output."""

from __future__ import annotations

from src.adapters.base import translate
from src.conformance.gate import ConformanceGate
from src.conformance.report import render_markdown
from src.conformance.results import CheckResult, HarnessResult
from tests.conformance_fixtures import SCENARIO, SENSORS, offset_adapter, real_streams

SENSOR_1, SENSOR_2 = SENSORS


def _results() -> list[HarnessResult]:
    gate = ConformanceGate()
    gate.submit(translate, SENSOR_1, SCENARIO, real_streams()[SENSOR_1.sensor_id])
    gate.submit(offset_adapter, SENSOR_2, SCENARIO, real_streams()[SENSOR_2.sensor_id])
    return gate.results()


def _table_rows(section: str) -> list[str]:
    return [line for line in section.splitlines() if line.startswith("| ") and "---" not in line][
        1:
    ]


def test_report_has_a_verdict_heading_and_seven_rows_per_adapter():
    report = render_markdown(_results())
    admitted, blocked = report.split("\n\n## ")
    assert admitted.startswith(f"## {SENSOR_1.sensor_id} — ADMITTED")
    assert blocked.startswith(f"{SENSOR_2.sensor_id} — BLOCKED")
    for section in (admitted, blocked):
        rows = _table_rows(section)
        assert len(rows) == 7
        assert [row.split(" | ")[0] for row in rows] == [f"| {n}" for n in range(1, 8)]


def test_report_shows_pass_and_fail_tokens_with_a_reason_per_row():
    report = render_markdown(_results())
    admitted, blocked = report.split("\n\n## ")
    assert all(" | PASS | " in row for row in _table_rows(admitted))
    fail_rows = [row for row in _table_rows(blocked) if " | FAIL | " in row]
    assert len(fail_rows) == 1 and fail_rows[0].startswith("| 4 | clock_offset | FAIL |")
    assert "2.000 s ahead" in fail_rows[0]
    for row in _table_rows(admitted) + _table_rows(blocked):
        reason = row.rsplit(" | ", 1)[1].rstrip(" |")
        assert reason.strip()


def test_report_escapes_pipes_in_reasons():
    check = CheckResult(number=1, name="schema", passed=False, reason="a | b")
    rest = [
        CheckResult(number=n, name=name, passed=True, reason="ok")
        for n, name in enumerate(
            [
                "units",
                "coordinate_frame",
                "clock_offset",
                "update_rate",
                "heartbeat",
                "dropped_messages",
            ],
            start=2,
        )
    ]
    report = render_markdown([HarnessResult(sensor_id="s", checks=(check, *rest))])
    assert "| 1 | schema | FAIL | a \\| b |" in report


def test_report_is_byte_identical_across_renders():
    assert render_markdown(_results()) == render_markdown(_results())


def test_report_for_no_adapters_is_empty():
    assert render_markdown([]) == ""
