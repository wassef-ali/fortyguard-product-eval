"""Pure-Python geometry helpers.

Only local math lives here: geodesic area, point-in-polygon, and nearest-tile
lookup. There is deliberately no geocoding and no network access, so the
pipeline stays FortyGuard-only.
"""

from __future__ import annotations

import math

# WGS84 authalic radius (metres): the sphere with the same surface area as the
# ellipsoid. Using the equatorial radius instead would overstate area ~0.3%.
_AUTHALIC_RADIUS_M = 6_371_007.181
_WGS84_F = 1.0 / 298.257223563
_WGS84_E2 = _WGS84_F * (2.0 - _WGS84_F)
_WGS84_E = math.sqrt(_WGS84_E2)

SQ_MI_TO_M2 = 2_589_988.110336
METRES_PER_DEG_LAT = 111_320.0


def _authalic_lat(phi_rad: float) -> float:
    """Geodetic latitude (radians) -> authalic latitude (radians)."""
    if not math.isfinite(phi_rad):
        return math.nan
    sin_phi = math.sin(phi_rad)
    es = _WGS84_E * sin_phi
    q = (1.0 - _WGS84_E2) * (
        sin_phi / (1.0 - es * es)
        - (1.0 / (2.0 * _WGS84_E)) * math.log((1.0 - es) / (1.0 + es))
    )
    qp = (1.0 - _WGS84_E2) * (
        1.0 / (1.0 - _WGS84_E2)
        - (1.0 / (2.0 * _WGS84_E)) * math.log((1.0 - _WGS84_E) / (1.0 + _WGS84_E))
    )
    return math.asin(max(-1.0, min(1.0, q / qp)))


def _unwrap_delta(a: float, b: float) -> float:
    d = b - a
    while d > 180.0:
        d -= 360.0
    while d < -180.0:
        d += 360.0
    return d


def _close_ring(ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not ring:
        return ring
    if ring[0] != ring[-1]:
        return [*ring, ring[0]]
    return ring


def ring_area_sq_miles(ring: list[tuple[float, float]]) -> float:
    """Geodesic area (spherical excess) of a closed [lon, lat] ring, in sq mi."""
    r = _close_ring(ring)
    if len(r) < 4:
        return 0.0
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(r, r[1:]):
        total += (
            math.radians(_unwrap_delta(lon1, lon2))
            * (
                2.0
                + math.sin(_authalic_lat(math.radians(lat1)))
                + math.sin(_authalic_lat(math.radians(lat2)))
            )
        )
    area_m2 = abs(total) * _AUTHALIC_RADIUS_M**2 / 2.0
    return area_m2 / SQ_MI_TO_M2


def _positions_to_ring(positions) -> list[tuple[float, float]]:
    ring: list[tuple[float, float]] = []
    for pos in positions or []:
        if isinstance(pos, (list, tuple)) and len(pos) >= 2:
            try:
                lon, lat = float(pos[0]), float(pos[1])
            except (TypeError, ValueError):
                return []
            if math.isfinite(lon) and math.isfinite(lat):
                ring.append((lon, lat))
    return ring


def extract_rings(aoi) -> list[list[tuple[float, float]]]:
    """Every exterior ring as [(lon, lat), ...] from a GeoJSON object."""
    if not isinstance(aoi, dict):
        return []
    t = aoi.get("type")
    if t == "FeatureCollection":
        out: list[list[tuple[float, float]]] = []
        for f in aoi.get("features") or []:
            out.extend(extract_rings(f))
        return out
    if t == "Feature":
        return extract_rings(aoi.get("geometry"))
    if t == "Polygon":
        coords = aoi.get("coordinates") or []
        ring = _positions_to_ring(coords[0]) if coords and coords[0] else []
        return [ring] if ring else []
    if t == "MultiPolygon":
        out: list[list[tuple[float, float]]] = []
        for poly in aoi.get("coordinates") or []:
            ring = _positions_to_ring(poly[0]) if poly and poly[0] else []
            if ring:
                out.append(ring)
        return out
    if "coordinates" in aoi:
        coords = aoi.get("coordinates")
        ring = _positions_to_ring(coords[0]) if isinstance(coords, list) and coords else []
        return [ring] if ring else []
    return []


def aoi_area_sq_miles(aoi) -> float:
    """Total exterior-ring area of a GeoJSON AOI, in square miles."""
    return sum(ring_area_sq_miles(r) for r in extract_rings(aoi))


def bbox_of_aoi(aoi) -> tuple[float, float, float, float] | None:
    """(west, south, east, north) over all rings, or None if unreadable."""
    points = [p for ring in extract_rings(aoi) for p in ring]
    if not points:
        return None
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    return (min(lons), min(lats), max(lons), max(lats))


def point_in_ring(lon: float, lat: float, ring: list[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test."""
    r = _close_ring(ring)
    inside = False
    for (ax, ay), (bx, by) in zip(r, r[1:]):
        if (ay > lat) != (by > lat):
            t = (lat - ay) / (by - ay)
            if lon < ax + t * (bx - ax):
                inside = not inside
    return inside


def point_in_aoi(lon: float, lat: float, aoi) -> bool:
    return any(point_in_ring(lon, lat, r) for r in extract_rings(aoi))


def grid_points(aoi, dimension: int = 5, max_points: int = 25) -> list[tuple[float, float]]:
    """Regular grid of (lat, lon) points inside the AOI."""
    bbox = bbox_of_aoi(aoi)
    if bbox is None:
        return []
    west, south, east, north = bbox
    xs = [west + (i + 0.5) * (east - west) / dimension for i in range(dimension)]
    ys = [south + (j + 0.5) * (north - south) / dimension for j in range(dimension)]
    points = [(lat, lon) for lat in ys for lon in xs if point_in_aoi(lon, lat, aoi)]
    if not points:
        return []
    if len(points) > max_points:
        stride = len(points) / max_points
        points = [points[int(i * stride)] for i in range(max_points)]
    return points


def nearest_tile(tiles: list[dict], lat: float, lon: float) -> dict | None:
    """Nearest tile centroid to (lat, lon); equirectangular with cos(lat) fix."""
    best: dict | None = None
    best_d = math.inf
    coslat = math.cos(math.radians(lat))
    for t in tiles:
        tlon, tlat = t.get("lon"), t.get("lat")
        if tlon is None or tlat is None:
            continue
        dx = (tlon - lon) * coslat
        dy = tlat - lat
        d = dx * dx + dy * dy
        if d < best_d:
            best_d, best = d, t
    return best


def nearest_tile_temperature(
    tiles: list[dict], lat: float, lon: float
) -> tuple[float, dict, float]:
    """Return (temperature_c, tile, distance_metres) for the nearest tile.

    Raises ValueError when there is no tile to source from (never invents a
    temperature).
    """
    tile = nearest_tile(tiles, lat, lon)
    if tile is None:
        raise ValueError("No heatmap tiles available to source a temperature from.")
    coslat = math.cos(math.radians(lat))
    dx_m = (tile["lon"] - lon) * coslat * METRES_PER_DEG_LAT
    dy_m = (tile["lat"] - lat) * METRES_PER_DEG_LAT
    distance_m = math.hypot(dx_m, dy_m)
    return float(tile["value"]), tile, distance_m
