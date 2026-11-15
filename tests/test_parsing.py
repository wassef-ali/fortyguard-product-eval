import pytest

from fortyguard import parsing


def _heatmap_result(result):
    return {"error": False, "data": {"activity_id": "abc", "status": "Completed", "result": result}}


def test_stats_mean_is_authoritative():
    """The explicit area mean wins over per-tile values."""
    response = _heatmap_result({
        "stats_data": {"temperature_stats": {
            "minimum": 29.2, "maximum": 31.5, "mean": 29.75386, "standard_deviation": 0.52,
        }},
        "map_data": {"type": "FeatureCollection", "features": [
            {"properties": {"tile_id": 0, "average_temperature": 40.0}},
        ]},
    })
    value, meta = parsing.extract_mean_temperature_c(response)
    assert value == pytest.approx(29.75386)
    assert meta["method"] == "stats_data_mean"


def test_tile_mean_fallback():
    response = _heatmap_result({
        "map_data": {"type": "FeatureCollection", "features": [
            {"properties": {"tile_id": 0, "average_temperature": 30.0}},
            {"properties": {"tile_id": 1, "average_temperature": 40.0}},
            {"properties": {"tile_id": 2, "average_temperature": None}},
        ]},
    })
    value, meta = parsing.extract_mean_temperature_c(response)
    assert value == pytest.approx(35.0)
    assert meta["method"] == "mean_of_heatmap_tiles"
    assert meta["tile_count"] == 2


def test_no_temperature_fails_closed():
    with pytest.raises(ValueError, match="no usable"):
        parsing.extract_mean_temperature_c(
            _heatmap_result({"stats_data": {"n_cells": 0}, "map_data": {"features": []}})
        )


def test_parse_env_params():
    response = {
        "data": {
            "result": {
                "metadata": {"timestamps": ["2024-07-15T05:00:00-07:00"]},
                "locations": [{
                    "lat": 33.4484, "lon": -112.074, "elevation": 333.0, "temperature": 29.567,
                    "parameters": {
                        "heat_index_celsius": [30.4],
                        "relative_humidity_percent": [50.3],
                    },
                    "solar_irradiance": {"clear_sky": {"ghi": 0.0}},
                }],
            }
        }
    }
    parsed = parsing.parse_env_params(response)
    assert parsed["input_temperature_c"] == 29.567
    assert parsed["parameters"]["heat_index_celsius"] == [30.4]
    assert parsed["timestamps"] == ["2024-07-15T05:00:00-07:00"]
