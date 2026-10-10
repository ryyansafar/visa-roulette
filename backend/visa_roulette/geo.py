"""Geography for the throw: great-circle travel and which country a landing falls in.

Uses the Natural Earth polygons already bundled in assets/ (no network, no shapely).
A landing in open water snaps to the nearest coastline vertex so the plane always ends on a country.
Callers may restrict the choice to countries that have a visa rule, so the booth never ends on "no rule on file".
"""

import dataclasses
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

COUNTRIES_PATH = Path(__file__).resolve().parents[2] / "assets" / "globe" / "countries.geojson"
EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class Country:
    iso3: str
    name: str


@dataclass(frozen=True)
class Landing:
    lat: float
    lon: float
    iso3: str
    name: str
    snapped: bool = False
    snap_km: float = 0.0
    distance_km: float = 0.0


@dataclass(frozen=True)
class _Shape:
    country: Country
    polygons: tuple  # each polygon: tuple of rings, ring = ndarray (n, 2) of lon, lat
    bbox: tuple  # min_lon, min_lat, max_lon, max_lat


def _wrap_lon(lon: float) -> float:
    return (lon + 180.0) % 360.0 - 180.0


def destination(lat: float, lon: float, heading_deg: float, distance_km: float) -> tuple:
    """Point reached travelling `distance_km` along a great circle; heading 0 = north, 90 = east."""
    phi1, lam1, theta = math.radians(lat), math.radians(lon), math.radians(heading_deg)
    delta = distance_km / EARTH_RADIUS_KM
    sin_phi2 = math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta)
    phi2 = math.asin(max(-1.0, min(1.0, sin_phi2)))
    lam2 = lam1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi1),
        math.cos(delta) - math.sin(phi1) * sin_phi2,
    )
    return math.degrees(phi2), _wrap_lon(math.degrees(lam2))


def _haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


@lru_cache(maxsize=1)
def _shapes() -> tuple:
    shapes = []
    for feature in json.loads(COUNTRIES_PATH.read_text())["features"]:
        props, geometry = feature["properties"], feature["geometry"]
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        rings = tuple(tuple(np.asarray(ring, dtype=float)[:, :2] for ring in poly) for poly in polygons)
        every = np.vstack([ring for poly in rings for ring in poly[:1]])
        bbox = (*every.min(axis=0), *every.max(axis=0))
        shapes.append(_Shape(Country(props["ADM0_A3"], props["NAME"]), rings, bbox))
    return tuple(shapes)


def _in_ring(ring: np.ndarray, lon: float, lat: float) -> bool:
    x, y = ring[:, 0], ring[:, 1]
    x2, y2 = np.roll(x, -1), np.roll(y, -1)
    crosses = (y > lat) != (y2 > lat)
    with np.errstate(divide="ignore", invalid="ignore"):
        x_at = (x2 - x) * (lat - y) / (y2 - y) + x
    return bool(np.count_nonzero(crosses & (lon < x_at)) % 2)


def _in_polygon(rings: tuple, lon: float, lat: float) -> bool:
    return _in_ring(rings[0], lon, lat) and not any(_in_ring(hole, lon, lat) for hole in rings[1:])


def country_at(lat: float, lon: float) -> Country | None:
    for shape in _shapes():
        min_lon, min_lat, max_lon, max_lat = shape.bbox
        if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
            continue
        if any(_in_polygon(poly, lon, lat) for poly in shape.polygons):
            return shape.country
    return None


def is_country(iso3: str) -> bool:
    return any(shape.country.iso3 == iso3 for shape in _shapes())


def countries() -> list:
    """Every country, by name, for pickers."""
    return sorted({shape.country for shape in _shapes()}, key=lambda c: c.name)


def country_name(iso3: str) -> str:
    for shape in _shapes():
        if shape.country.iso3 == iso3:
            return shape.country.name
    raise ValueError(f"unknown country code: {iso3}")


def country_centroid(iso3: str) -> tuple:
    """Centre of the country's largest mainland ring: a stable starting point for a throw."""
    for shape in _shapes():
        if shape.country.iso3 != iso3:
            continue
        ring = max((poly[0] for poly in shape.polygons), key=lambda r: np.ptp(r[:, 0]) * np.ptp(r[:, 1]))
        return float((ring[:, 1].min() + ring[:, 1].max()) / 2), float((ring[:, 0].min() + ring[:, 0].max()) / 2)
    raise ValueError(f"unknown country code: {iso3}")


@lru_cache(maxsize=1)
def _coast() -> tuple:
    points, owners = [], []
    for shape in _shapes():
        for poly in shape.polygons:
            points.append(poly[0])
            owners.extend([shape.country] * len(poly[0]))
    return np.vstack(points), tuple(owners)


def land(lat: float, lon: float, only: frozenset | None = None) -> Landing:
    """Resolve a point to a country, snapping to the nearest coastline vertex when it is open water
    or (if `only` is given) a country outside that set."""
    found = country_at(lat, lon)
    if found is not None and (only is None or found.iso3 in only):
        return Landing(lat, lon, found.iso3, found.name)
    coast, owners = _coast()
    gaps = _haversine_km(lat, lon, coast[:, 1], coast[:, 0])
    if only is not None:
        gaps = np.where([owner.iso3 in only for owner in owners], gaps, np.inf)
        if not np.isfinite(gaps).any():
            raise ValueError("no allowed country to land on")
    nearest = int(np.argmin(gaps))
    owner = owners[nearest]
    return Landing(
        float(coast[nearest, 1]), float(coast[nearest, 0]), owner.iso3, owner.name, True, float(gaps[nearest])
    )


def resolve_landing(origin_iso3: str, heading_deg: float, distance_km: float, only: frozenset | None = None) -> Landing:
    start_lat, start_lon = country_centroid(origin_iso3)
    lat, lon = destination(start_lat, start_lon, heading_deg, distance_km)
    result = land(lat, lon, only)
    flown = float(_haversine_km(start_lat, start_lon, result.lat, result.lon))
    return dataclasses.replace(result, distance_km=flown)
