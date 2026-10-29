"""Ground-truth trajectory generation for drones, birds, and clutter.

Each generator produces a ``TruthObject``: a named, kinded sequence of
timestamped positions that ``src.simulator.detections`` samples when
building each sensor's noisy, rate-limited raw detection stream.

All randomness flows through the caller-provided ``numpy.random.Generator``
(see ``src.simulator.rng``), never the global ``random``/``numpy.random``
state, so the same seed always reproduces the same trajectories.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from src.config.models import BirdTarget, ClutterConfig, DefendedArea, DroneTarget
from src.simulator.geo import latlon_to_offset, offset_to_latlon


@dataclass(frozen=True)
class TruthSample:
    """A single ground-truth position at a point in simulated time."""

    t_s: float
    lat: float
    lon: float
    alt_m: float


@dataclass(frozen=True)
class TruthObject:
    """A named, kinded object with a time-ordered sequence of truth samples."""

    object_id: str
    kind: str  # "drone" | "bird" | "clutter"
    samples: tuple[TruthSample, ...]

    def position_at(self, t_s: float) -> TruthSample | None:
        """Return the object's (linearly interpolated) position at ``t_s``.

        Returns ``None`` if ``t_s`` is before the object's first sample or
        after its last -- i.e. the object does not exist yet, or anymore,
        at that time.
        """
        samples = self.samples
        if not samples or t_s < samples[0].t_s or t_s > samples[-1].t_s:
            return None
        if len(samples) == 1:
            return samples[0]

        # Find the bracketing pair [a, b] with a.t_s <= t_s <= b.t_s.
        lo, hi = 0, len(samples) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if samples[mid].t_s <= t_s:
                lo = mid
            else:
                hi = mid
        a, b = samples[lo], samples[hi]
        if b.t_s == a.t_s:
            return a
        frac = (t_s - a.t_s) / (b.t_s - a.t_s)
        return TruthSample(
            t_s=t_s,
            lat=a.lat + frac * (b.lat - a.lat),
            lon=a.lon + frac * (b.lon - a.lon),
            alt_m=a.alt_m + frac * (b.alt_m - a.alt_m),
        )


def generate_drone_trajectory(
    rng: np.random.Generator,
    defended_area: DefendedArea,
    drone: DroneTarget,
    truth_dt_s: float = 0.5,
) -> TruthObject:
    """A drone flies a straight line through the area at constant speed/altitude.

    It starts ``start_range_m`` out at ``start_bearing_deg`` and continues
    in a straight line through the center and out the opposite side, so
    sensors get to track both its approach and recession.
    """
    bearing_rad = math.radians(drone.start_bearing_deg)
    # Unit vector pointing from the center toward the start position (i.e.
    # the compass bearing the drone starts at, relative to center).
    out_east, out_north = math.sin(bearing_rad), math.cos(bearing_rad)
    start_east = out_east * drone.start_range_m
    start_north = out_north * drone.start_range_m
    # The drone flies inbound, i.e. the reverse of the outward direction.
    in_east, in_north = -out_east, -out_north

    total_path_m = 2.0 * drone.start_range_m
    duration_s = total_path_m / drone.speed_mps
    # Small, reproducible altitude jitter so the track isn't perfectly flat.
    alt_jitter_m = rng.normal(0.0, 2.0)

    samples = []
    n_ticks = math.floor(duration_s / truth_dt_s) + 1
    for i in range(n_ticks):
        t_s = min(i * truth_dt_s, duration_s)
        dist_traveled_m = drone.speed_mps * t_s
        east_m = start_east + in_east * dist_traveled_m
        north_m = start_north + in_north * dist_traveled_m
        lat, lon = offset_to_latlon(
            defended_area.center_lat, defended_area.center_lon, east_m, north_m
        )
        samples.append(
            TruthSample(t_s=t_s, lat=lat, lon=lon, alt_m=drone.altitude_m + alt_jitter_m)
        )

    return TruthObject(object_id=drone.target_id, kind="drone", samples=tuple(samples))


def generate_bird_trajectory(
    rng: np.random.Generator,
    defended_area: DefendedArea,
    bird: BirdTarget,
    duration_s: float,
    truth_dt_s: float = 1.0,
) -> TruthObject:
    """A bird performs a slower, erratic random walk, loosely bounded to the area.

    Heading drifts randomly every ``heading_change_period_s``; if the bird
    wanders too far from the area it's nudged back toward the center.
    """
    east_m, north_m = latlon_to_offset(
        defended_area.center_lat, defended_area.center_lon, bird.start_lat, bird.start_lon
    )
    heading_rad = rng.uniform(0.0, 2.0 * math.pi)
    bound_radius_m = defended_area.radius_m * 1.3

    samples = [
        TruthSample(
            t_s=0.0,
            lat=bird.start_lat,
            lon=bird.start_lon,
            alt_m=bird.altitude_m,
        )
    ]
    t_s = 0.0
    time_since_heading_change_s = 0.0
    while t_s < duration_s:
        step_s = min(truth_dt_s, duration_s - t_s)
        t_s += step_s
        time_since_heading_change_s += step_s

        if time_since_heading_change_s >= bird.heading_change_period_s:
            heading_rad += rng.normal(0.0, math.pi / 3.0)
            time_since_heading_change_s = 0.0

        distance_from_center_m = math.hypot(east_m, north_m)
        if distance_from_center_m > bound_radius_m:
            # Nudge heading back toward the center, with a little scatter.
            heading_rad = math.atan2(-east_m, -north_m) + rng.normal(0.0, math.pi / 8.0)

        speed_mps = max(0.1, bird.speed_mps + rng.normal(0.0, 0.5))
        east_m += math.sin(heading_rad) * speed_mps * step_s
        north_m += math.cos(heading_rad) * speed_mps * step_s

        lat, lon = offset_to_latlon(
            defended_area.center_lat, defended_area.center_lon, east_m, north_m
        )
        samples.append(
            TruthSample(t_s=t_s, lat=lat, lon=lon, alt_m=bird.altitude_m + rng.normal(0.0, 1.0))
        )

    return TruthObject(object_id=bird.target_id, kind="bird", samples=tuple(samples))


def generate_clutter_trajectories(
    rng: np.random.Generator,
    defended_area: DefendedArea,
    clutter: ClutterConfig,
    duration_s: float,
) -> list[TruthObject]:
    """Random, short-lived, stationary clutter blips scattered across the area.

    Each blip appears at a random time and a random point within the
    defended area's radius, stays still for ``dwell_s``, then vanishes.
    """
    objects = []
    for i in range(clutter.count):
        start_t_s = rng.uniform(0.0, max(0.0, duration_s - clutter.dwell_s))
        # Uniform point within a disk: radius ~ sqrt(u) avoids center bunching.
        radius_m = defended_area.radius_m * math.sqrt(rng.uniform(0.0, 1.0))
        angle_rad = rng.uniform(0.0, 2.0 * math.pi)
        east_m = radius_m * math.sin(angle_rad)
        north_m = radius_m * math.cos(angle_rad)
        lat, lon = offset_to_latlon(
            defended_area.center_lat, defended_area.center_lon, east_m, north_m
        )
        end_t_s = start_t_s + clutter.dwell_s
        samples = (
            TruthSample(t_s=start_t_s, lat=lat, lon=lon, alt_m=clutter.altitude_m),
            TruthSample(t_s=end_t_s, lat=lat, lon=lon, alt_m=clutter.altitude_m),
        )
        objects.append(TruthObject(object_id=f"clutter-{i}", kind="clutter", samples=samples))
    return objects
