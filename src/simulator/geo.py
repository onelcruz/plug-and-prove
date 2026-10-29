"""Small flat-earth lat/lon <-> local-meters helpers for the simulator.

This is a simple equirectangular approximation, valid over the few-kilometer
scale a single defended area covers (architecture.md §3.2 makes the same
"small area" assumption for the fusion engine's internal ENU frame). The
simulator uses it to place targets and compute sensor-to-target range in
meters, then converts back to WGS84 lat/lon for its output -- the simulator
itself never exposes local coordinates; only the fusion engine's internal
ENU frame (a separate, later concern) does.
"""

from __future__ import annotations

import math

_EARTH_RADIUS_M = 6_371_000.0
_METERS_PER_DEGREE_LAT = (math.pi / 180.0) * _EARTH_RADIUS_M


def _meters_per_degree_lon(at_lat_deg: float) -> float:
    return _METERS_PER_DEGREE_LAT * math.cos(math.radians(at_lat_deg))


def offset_to_latlon(
    base_lat: float, base_lon: float, east_m: float, north_m: float
) -> tuple[float, float]:
    """Convert an East/North meter offset from ``(base_lat, base_lon)`` to lat/lon."""
    lat = base_lat + north_m / _METERS_PER_DEGREE_LAT
    lon = base_lon + east_m / _meters_per_degree_lon(base_lat)
    return lat, lon


def latlon_to_offset(
    base_lat: float, base_lon: float, lat: float, lon: float
) -> tuple[float, float]:
    """Convert ``(lat, lon)`` to an East/North meter offset from ``(base_lat, base_lon)``."""
    north_m = (lat - base_lat) * _METERS_PER_DEGREE_LAT
    east_m = (lon - base_lon) * _meters_per_degree_lon(base_lat)
    return east_m, north_m


def distance_m(base_lat: float, base_lon: float, lat: float, lon: float) -> float:
    """Straight-line ground distance in meters between two lat/lon points."""
    east_m, north_m = latlon_to_offset(base_lat, base_lon, lat, lon)
    return math.hypot(east_m, north_m)
