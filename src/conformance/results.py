"""Result types for the conformance harness (specs/007-conformance-harness/data-model.md)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CHECK_NAMES: tuple[str, ...] = (
    "schema",
    "units",
    "coordinate_frame",
    "clock_offset",
    "update_rate",
    "heartbeat",
    "dropped_messages",
)


class CheckResult(BaseModel):
    """The outcome of one of the seven contract checks."""

    model_config = ConfigDict(frozen=True)

    number: int = Field(..., ge=1, le=len(CHECK_NAMES))
    name: str
    passed: bool
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason_is_one_non_empty_line(cls, reason: str) -> str:
        if not reason.strip():
            raise ValueError("reason must not be empty")
        if "\n" in reason or "\r" in reason:
            raise ValueError("reason must be a single line")
        return reason

    @model_validator(mode="after")
    def _name_matches_number(self) -> CheckResult:
        expected = CHECK_NAMES[self.number - 1]
        if self.name != expected:
            raise ValueError(f"check {self.number} must be named {expected!r}, got {self.name!r}")
        return self


class HarnessResult(BaseModel):
    """All seven check outcomes for one adapter; ``admitted`` iff every check passed."""

    model_config = ConfigDict(frozen=True)

    sensor_id: str
    checks: tuple[CheckResult, ...]

    @model_validator(mode="after")
    def _exactly_seven_checks_in_order(self) -> HarnessResult:
        numbers = tuple(c.number for c in self.checks)
        if numbers != tuple(range(1, len(CHECK_NAMES) + 1)):
            raise ValueError(
                f"checks must be numbered 1-{len(CHECK_NAMES)} in order, got {numbers}"
            )
        return self

    @property
    def admitted(self) -> bool:
        return all(c.passed for c in self.checks)
