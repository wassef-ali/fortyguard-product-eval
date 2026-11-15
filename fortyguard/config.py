"""Configuration and constants for the FortyGuard-only analyzer.

Nothing here is account-specific. Plan limits (Basic vs Pro) are documented
constants used only to WARN before spending credits; the API is always the
authority on what an account may actually do.
"""

from __future__ import annotations

# Base URL without a trailing slash. All routes below are the /v1 paths.
FORTYGUARD_BASE_URL = "https://api.fortyguard.com"

HEATMAP_PATH = "/v1/heatmap"
ENV_PARAMS_PATH = "/v1/env_params"
STATUS_PATH = "/v1/status/{activity_id}"
USAGE_PATH = "/v1/system/fetch-api-key-usage"

# Heatmap tile edge sizes, in metres. The API accepts 60, 80 or 100.
HEATMAP_GRANULARITY_M = {"high": 60, "medium": 80, "low": 100}

# date_time.filter_type values (documented).
FILTER_TYPE = {
    "single_hour": 1,   # start_date + start_time
    "hours_range": 2,   # start_date + start_time + end_time
    "single_day": 3,    # start_date only
    "days_range": 4,    # start_date + end_date
}

# All env_params `analysis` names. Omitting `analysis` returns all of them.
ENV_ANALYSES = [
    "heat_index_celsius",
    "apparent_temperature_celsius",
    "wet_bulb_temperature_celsius",
    "relative_humidity_percent",
    "precipitation_mm",
    "cloud_cover_octas",
    "elevation",
    "solar_irradiance",
    "air_quality:idx",
    "air_quality_pm2p5:idx",
    "air_quality_pm10:idx",
    "air_quality_no2:idx",
    "air_quality_o3:idx",
    "air_quality_so2:idx",
    "aqi_us_co",
    "methane_ppb",
    "co2_ppm",
]

# Default selection respecting the Basic plan ("up to 3 user-selected").
DEFAULT_ANALYSES = [
    "heat_index_celsius",
    "wet_bulb_temperature_celsius",
    "relative_humidity_percent",
]

# Published Basic-plan ceilings (fortyguard.com/api-pricing). Warnings only.
BASIC_MAX_AREA_SQ_MI = 10
BASIC_MAX_ENV_ANALYSES = 3

# Test city.
DEFAULT_TIMEZONE = "America/Phoenix"
DEFAULT_CITY = "Phoenix, Arizona"

# Local (area-of-interest) hour for single-hour analyses (filter_type: 1).
# env_params is a point-in-time measurement, so it needs an hour, not a day.
# Override with --time in cli.py or the time input in app.py.
DEFAULT_START_TIME = "14:00"

# Small manually-defined AOI near Downtown Phoenix, well under the 10 sq mi cap
# (measured ~0.08 sq mi). Coordinates are [longitude, latitude] per GeoJSON.
PHOENIX_AOI = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"name": "Downtown Phoenix small test AOI"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-112.0780, 33.4510],
                        [-112.0730, 33.4510],
                        [-112.0730, 33.4550],
                        [-112.0780, 33.4550],
                        [-112.0780, 33.4510],
                    ]
                ]
            },
        }
    ],
}

# (latitude, longitude) representative point inside PHOENIX_AOI.
PHOENIX_CENTER = (33.4530, -112.0755)
