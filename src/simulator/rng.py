"""Central seeded RNG utility.

Constitution principle V (Reproducibility) requires that all randomness in
Plug-and-Prove flows through this module. Never call ``random`` or
``numpy.random`` directly in simulator, adapter, or test code — use
``get_rng`` or ``spawn_rngs`` instead, so a single top-level seed
deterministically reproduces an entire run.
"""

from __future__ import annotations

import numpy as np
from numpy.random import Generator

__all__ = ["Generator", "get_rng", "spawn_rngs"]


def get_rng(seed: int) -> np.random.Generator:
    """Return a freshly seeded, independent NumPy random Generator.

    Uses ``numpy.random.default_rng`` (PCG64) rather than the legacy global
    ``numpy.random`` state, so multiple components never interfere with each
    other's randomness while remaining fully reproducible from one seed.
    """
    return np.random.default_rng(seed)


def spawn_rngs(seed: int, n: int) -> list[np.random.Generator]:
    """Derive ``n`` independent, reproducible child RNG streams from one seed.

    Useful for giving each simulated sensor (or sub-system) its own
    independent random stream without correlating them, while the entire set
    remains fully determined by the single top-level seed.
    """
    root = np.random.SeedSequence(seed)
    child_seqs = root.spawn(n)
    return [np.random.default_rng(seq) for seq in child_seqs]
