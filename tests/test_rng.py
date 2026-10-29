from src.simulator.rng import get_rng, spawn_rngs


def test_get_rng_reproducible():
    a = get_rng(123).random(5)
    b = get_rng(123).random(5)
    assert list(a) == list(b)


def test_get_rng_different_seeds_differ():
    a = get_rng(1).random(5)
    b = get_rng(2).random(5)
    assert list(a) != list(b)


def test_spawn_rngs_reproducible_across_runs():
    run1 = [rng.random(3).tolist() for rng in spawn_rngs(seed=7, n=3)]
    run2 = [rng.random(3).tolist() for rng in spawn_rngs(seed=7, n=3)]
    assert run1 == run2


def test_spawn_rngs_independent_streams():
    streams = spawn_rngs(seed=7, n=3)
    draws = [rng.random(3).tolist() for rng in streams]
    assert draws[0] != draws[1]
    assert draws[1] != draws[2]
