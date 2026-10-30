"""Canonical pipeline messages produced by sensor adapters (architecture.md §3.1, §3.4).

``Detection`` is the schema every adapter (present and future) must emit, enforced
with pydantic so the conformance harness (#7) gets free, structured validation
errors. ``Heartbeat`` is the explicit schedule-coverage signal introduced by the
sensor adapter contract (#6): emitted for any scheduled tick where no target was
in view, so a consumer can tell "nothing to report this tick" apart from a tick
that was never produced at all.

``Heartbeat`` is **not** real sensor-liveness/failure detection -- see
specs/006-sensor-adapter-contract/plan.md's "Known limitation" for why that
remains out of scope here. Only the conformance harness consumes ``Heartbeat``;
the fusion engine never sees it (architecture.md §5's locked
"canonical Detection objects (post-harness-gate)" input contract).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, NonNegativeFloat, PositiveFloat


class Detection(BaseModel):
    """The canonical, schema-validated message every adapter emits (architecture.md §3.1)."""

    sensor_id: str
    detection_id: str
    timestamp_utc: NonNegativeFloat
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    alt_m: float
    accuracy_m: PositiveFloat
    velocity_mps: float | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    raw_payload: dict


class Heartbeat(BaseModel):
    """Explicit schedule-coverage signal for a scheduled tick with no ``Detection``.

    ``timestamp_utc`` is computed via the same ``start_utc + t_s`` conversion
    ``Detection`` uses, so both message types share one time base. ``t_s`` is
    retained alongside it but is informational/debugging only, matching
    ``Detection.raw_payload``'s existing "debugging only" convention -- it is not
    a contract field any consumer should rely on for timing logic.
    """

    sensor_id: str
    timestamp_utc: NonNegativeFloat
    t_s: NonNegativeFloat
