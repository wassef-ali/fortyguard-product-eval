"""Local-only heatmap rendering (no basemap, no external tiles)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PatchCollection
from matplotlib.colors import Normalize
from matplotlib.patches import Polygon as MplPolygon


def render_heatmap(result: dict, out_path: Path, title: str = "FortyGuard street-level temperature") -> Path:
    """Render heatmap tiles as coloured polygons from data.result.map_data.

    Raises ValueError when there are no tiles to render (an empty result).
    """
    map_data = result.get("map_data") or {}
    features = map_data.get("features") or []
    patches = []
    values = []
    for feature in features:
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coords = (geometry.get("coordinates") or [[]])[0]
        value = props.get("average_temperature", props.get("value"))
        if value is None or not coords:
            continue
        try:
            xy = [(float(p[0]), float(p[1])) for p in coords]
        except (TypeError, ValueError):
            continue
        if len(xy) < 3:
            continue
        patches.append(MplPolygon(xy, closed=True, linewidth=0))
        values.append(float(value))

    if not patches or not values:
        raise ValueError("No heatmap tiles to render (empty result).")

    fig, ax = plt.subplots(figsize=(10, 8))
    norm = Normalize(vmin=min(values), vmax=max(values))
    collection = PatchCollection(patches, cmap="turbo", norm=norm)
    collection.set_array(values)
    ax.add_collection(collection)
    ax.autoscale()
    ax.set_aspect("equal")
    ax.set_title(f"{title} (°C)")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    fig.colorbar(collection, ax=ax, label="°C")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out_path
