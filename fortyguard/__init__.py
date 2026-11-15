"""FortyGuard-only environmental analyzer.

A clean, dependency-light pipeline over the FortyGuard Temperature API:
heatmap generation, exact mean-temperature extraction, nearest-tile
temperature sourcing, and point-level environmental parameters.

No third-party weather source (Open-Meteo) and no external geocoder
(Nominatim) are used anywhere in this package.
"""

__all__ = ["client", "config", "geo", "parsing", "archive", "visualization"]
