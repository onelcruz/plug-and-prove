"""Human-readable Markdown conformance report (architecture.md §4, research.md R10)."""

from __future__ import annotations

from collections.abc import Sequence

from src.conformance.results import HarnessResult


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def render_markdown(results: Sequence[HarnessResult]) -> str:
    """Render one section per adapter: a verdict heading and a 7-row check table.

    No timestamps are included, so identical results always render byte-identically.
    """
    sections: list[str] = []
    for result in results:
        verdict = "ADMITTED" if result.admitted else "BLOCKED"
        lines = [
            f"## {result.sensor_id} — {verdict}",
            "",
            "| # | Check | Result | Reason |",
            "|---|-------|--------|--------|",
        ]
        for check in result.checks:
            outcome = "PASS" if check.passed else "FAIL"
            lines.append(f"| {check.number} | {check.name} | {outcome} | {_cell(check.reason)} |")
        sections.append("\n".join(lines))
    return "\n\n".join(sections) + "\n" if sections else ""
