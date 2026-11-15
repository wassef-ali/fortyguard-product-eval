import pytest

from fortyguard import geo
from fortyguard.config import PHOENIX_AOI, PHOENIX_CENTER


def test_phoenix_aoi_is_small():
    area = geo.aoi_area_sq_miles(PHOENIX_AOI)
    # Roughly 0.08 sq mi — comfortably under the Basic 10 sq mi cap.
    assert 0.03 < area < 0.5


def test_center_is_inside_aoi():
    lat, lon = PHOENIX_CENTER
    assert geo.point_in_aoi(lon, lat, PHOENIX_AOI)


def test_nearest_tile_temperature():
    tiles = [
        {"tile_id": 0, "lon": -112.075, "lat": 33.453, "value": 30.0},
        {"tile_id": 1, "lon": -112.070, "lat": 33.453, "value": 40.0},
    ]
    temp, tile, dist = geo.nearest_tile_temperature(tiles, 33.453, -112.0755)
    assert temp == pytest.approx(30.0)
    assert tile["tile_id"] == 0


def test_nearest_tile_fails_closed_when_empty():
    with pytest.raises(ValueError, match="No heatmap tiles"):
        geo.nearest_tile_temperature([], 33.453, -112.0755)
