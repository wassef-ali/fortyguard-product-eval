"""Parsing FortyGuard responses — matched to the real API shapes.

Heatmap `data.result` shapes:

  temperature  map_data.features[].properties carries tile_id, average_temperature,
               min_temperature, max_temperature; stats_data.temperature_stats
               carries minimum, maximum, mean, standard_deviation.
  analytic     properties carries tile_id, value; stats_data carries
               analytic_type, units, n_cells, min, max, mean.
  empty        map_data.features == []; stats_data is {activity_id, n_cells: 0}
               (and is still charged in full).

env_params `data.result` shape:

  metadata.timestamps[] plus locations[]; each location has lat, lon, elevation,
  temperature (the value that was passed in), parameters {name: [values aligned
  to timestamps]}, and solar_irradiance.
"""

from __future__ import annotations

import math
from typing import Any


def _result(response: dict) -> dict:
    data = response.get("data") or {}
    result = data.get("result")
    return result if isinstance(result, dict) else {}


def _num(value: Any) -> float | None:
    """A finite float, or None. Bools and non-finite values are refused."""
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def stats_mean(result: dict) -> float | None:
    """Explicit area mean, read from stats_data (the authoritative value)."""
    stats = result.get("stats_data")
    if not isinstance(stats, dict):
        return None
    ts = stats.get("temperature_stats")
    if isinstance(ts, dict):
        value = _num(ts.get("mean"))
        if value is not None:
            return value
    # Analytic shape exposes mean directly on stats_data.
    return _num(stats.get("mean"))


def _centroid(feature: dict) -> tuple[float | None, float | None]:
    try:
        ring = (feature.get("geometry") or {}).get("coordinates") or [[]]
        pts = ring[0][:-1] if ring and ring[0] else []
        if not pts:
            return (None, None)
        lon = sum(p[0] for p in pts) / len(pts)
        lat = sum(p[1] for p in pts) / len(pts)
    except (TypeError, IndexError, KeyError, ValueError, ZeroDivisionError):
        return (None, None)
    if not (math.isfinite(lon) and math.isfinite(lat)):
        return (None, None)
    return (lon, lat)


def tiles(result: dict) -> list[dict]:
    """Tiles as [{tile_id, lon, lat, value, min, max}], across all shapes.

    `value` is average_temperature (temperature shape) or value (analytic
    shape). Tiles with unreadable values are skipped individually.
    """
    out: list[dict] = []
    map_data = result.get("map_data")
    features = map_data.get("features") if isinstance(map_data, dict) else None
    if not isinstance(features, list):
        return out
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties")
        if not isinstance(props, dict):
            continue
        if "average_temperature" in props:
            value = _num(props["average_temperature"])
            vmin = _num(props.get("min_temperature"))
            vmax = _num(props.get("max_temperature"))
        elif "value" in props:
            value = _num(props["value"])
            vmin = vmax = None
        else:
            continue
        if value is None:
            continue
        try:
            tile_id = int(props.get("tile_id", index))
        except (TypeError, ValueError):
            tile_id = index
        lon, lat = _centroid(feature)
        out.append(
            {
                "tile_id": tile_id,
                "lon": lon,
                "lat": lat,
                "value": value,
                "min": vmin,
                "max": vmax,
            }
        )
    return out


def extract_mean_temperature_c(response: dict) -> tuple[float, dict]:
    """Return (mean_c, provenance). Fails closed if no valid temperature exists.

    Prefer the explicit area mean in stats_data. Only when it is absent fall
    back to an unweighted mean of per-tile values. Never interprets unrelated
    numbers as temperature and never consults an external weather source.
    """
    result = _result(response)

    mean = stats_mean(result)
    if mean is not None:
        return mean, {
            "method": "stats_data_mean",
            "source": "stats_data.temperature_stats.mean",
            "temperature_c": mean,
        }

    ts = tiles(result)
    values = [t["value"] for t in ts]
    if not values:
        raise ValueError(
            "Completed heatmap response contains no usable mean or tile "
            "temperatures. No external weather source is used as a fallback; "
            "inspect the saved raw response instead."
        )
    computed = sum(values) / len(values)
    return computed, {
        "method": "mean_of_heatmap_tiles",
        "tile_count": len(values),
        "temperature_c": computed,
    }


def parse_env_params(response: dict) -> dict:
    """Flatten an env_params result into a small, stable dict."""
    result = _result(response)
    locations = result.get("locations") or []
    metadata = result.get("metadata") or {}
    if not locations:
        raise ValueError("env_params result contains no locations[].")
    location = locations[0]
    parameters = location.get("parameters") or {}
    return {
        "lat": location.get("lat"),
        "lon": location.get("lon"),
        "elevation": location.get("elevation"),
        "input_temperature_c": location.get("temperature"),
        "timestamps": metadata.get("timestamps") or [],
        "parameters": parameters,
        "solar_irradiance": location.get("solar_irradiance"),
    }
