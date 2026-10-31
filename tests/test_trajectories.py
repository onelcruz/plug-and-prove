from src.config.models import BirdTarget, ClutterConfig, DefendedArea, DroneTarget
from src.simulator.rng import get_rng
from src.simulator.trajectories import (
    generate_bird_trajectory,
    generate_clutter_trajectories,
    generate_drone_trajectory,
)

AREA = DefendedArea(center_lat=38.8895, center_lon=-77.0353, radius_m=2000)


def test_drone_trajectory_reproducible():
    drone = DroneTarget(
        target_id="d1", start_bearing_deg=90, start_range_m=2000, speed_mps=20, altitude_m=100
    )
    a = generate_drone_trajectory(get_rng(1), AREA, drone)
    b = generate_drone_trajectory(get_rng(1), AREA, drone)
    assert a.samples == b.samples


def test_drone_trajectory_starts_at_configured_bearing():
    # Regression test for a bug (caught in independent code review of #5)
    # where start position was placed 180deg opposite the configured bearing.
    # bearing 0 = north (+lat), 90 = east (+lon), 180 = south (-lat), 270 = west (-lon).
    east_drone = DroneTarget(
        target_id="d1", start_bearing_deg=90, start_range_m=2000, speed_mps=20, altitude_m=100
    )
    north_drone = DroneTarget(
        target_id="d2", start_bearing_deg=0, start_range_m=2000, speed_mps=20, altitude_m=100
    )
    east_first = generate_drone_trajectory(get_rng(1), AREA, east_drone).samples[0]
    north_first = generate_drone_trajectory(get_rng(1), AREA, north_drone).samples[0]
    assert east_first.lon > AREA.center_lon  # starts east of center
    assert north_first.lat > AREA.center_lat  # starts north of center


def test_drone_trajectory_approaches_then_recedes_from_center():
    drone = DroneTarget(
        target_id="d1", start_bearing_deg=0, start_range_m=2000, speed_mps=20, altitude_m=100
    )
    traj = generate_drone_trajectory(get_rng(1), AREA, drone)
    distances = [
        ((s.lat - AREA.center_lat) ** 2 + (s.lon - AREA.center_lon) ** 2) ** 0.5
        for s in traj.samples
    ]
    midpoint = len(distances) // 2
    # Starts far from center, passes near it, ends far again.
    assert distances[0] > distances[midpoint]
    assert distances[-1] > distances[midpoint]


def test_drone_trajectory_position_at_outside_window_is_none():
    drone = DroneTarget(
        target_id="d1", start_bearing_deg=0, start_range_m=1000, speed_mps=20, altitude_m=100
    )
    traj = generate_drone_trajectory(get_rng(1), AREA, drone)
    last_t = traj.samples[-1].t_s
    assert traj.position_at(-1.0) is None
    assert traj.position_at(last_t + 1000.0) is None
    assert traj.position_at(last_t / 2.0) is not None


def test_bird_trajectory_reproducible_and_spans_full_duration():
    bird = BirdTarget(target_id="b1", start_lat=38.89, start_lon=-77.03, speed_mps=6, altitude_m=40)
    a = generate_bird_trajectory(get_rng(2), AREA, bird, duration_s=60)
    b = generate_bird_trajectory(get_rng(2), AREA, bird, duration_s=60)
    assert a.samples == b.samples
    assert a.samples[0].t_s == 0.0
    assert a.samples[-1].t_s == 60.0


def test_clutter_trajectories_count_and_short_lived():
    clutter = ClutterConfig(count=5, dwell_s=2.0)
    objects = generate_clutter_trajectories(get_rng(3), AREA, clutter, duration_s=100)
    assert len(objects) == 5
    for obj in objects:
        assert obj.kind == "clutter"
        # Stationary: both samples at the same position, dwell_s apart.
        assert obj.samples[0].lat == obj.samples[1].lat
        assert obj.samples[0].lon == obj.samples[1].lon
        assert obj.samples[1].t_s - obj.samples[0].t_s == 2.0
