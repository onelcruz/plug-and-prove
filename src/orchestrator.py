"""Entry point tying every Plug-and-Prove component together.

See architecture.md §2 (component 9) and §10 (end-to-end data flow).

This is currently a placeholder. Full wiring — loading config, seeding the
RNG, registering adapters behind the conformance harness gate, and driving
the simulation loop through fusion, classification, recommendation, and
output — lands in issue #13, once every other component exists.
"""

from __future__ import annotations


def main() -> None:  # pragma: no cover - placeholder until #13
    raise NotImplementedError("Orchestrator wiring lands in issue #13.")


if __name__ == "__main__":  # pragma: no cover
    main()
