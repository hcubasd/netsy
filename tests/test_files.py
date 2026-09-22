import geopandas
import pandas as pd
import pytest
from shapely.geometry import Point, box

from netsy.helpers.files import read_aggregate, read_distribution, read_zones


def _csv(tmp_path, text, name="table.csv"):
    path = tmp_path / name
    path.write_text(text)
    return str(path)


def test_read_aggregate_keeps_everything_as_text(tmp_path):
    table = read_aggregate(_csv(tmp_path, "zone_id,sector,grain\n1,NA,2.0\n2,b,\n"))
    assert table["zone_id"].tolist() == ["1", "2"]
    assert table["sector"].tolist() == ["NA", "b"]
    assert table["grain"].tolist()[0] == "2.0" and pd.isna(table["grain"].tolist()[1])


def test_read_aggregate_missing_file(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        read_aggregate(str(tmp_path / "missing.csv"))


def test_read_distribution_types_the_level_and_probability(tmp_path):
    table = read_distribution(_csv(tmp_path, "zone_id,resource,resource_level,probability\n1,grain,2,0.4\n1,grain,5,0.6\n"))
    assert table["zone_id"].tolist() == ["1", "1"]
    assert str(table["resource_level"].dtype) == "int64"
    assert table["probability"].dtype == float


def test_read_distribution_accepts_levels_written_as_floats(tmp_path):
    table = read_distribution(_csv(tmp_path, "zone_id,resource,resource_level,probability\n1,grain,2.0,1\n"))
    assert str(table["resource_level"].dtype) == "int64"


@pytest.mark.parametrize("row, message", [
    ("1,grain,-1,1.0", "whole numbers"),
    ("1,grain,2.5,1.0", "whole numbers"),
    ("1,grain,2,1.5", "between 0 and 1"),
    ("1,grain,2,-0.1", "between 0 and 1"),
    ("1,grain,two,1.0", "must be numbers"),
    ("1,grain,,1.0", "whole numbers"),
    ("1,grain,2,", "between 0 and 1"),
])
def test_read_distribution_rejects_bad_rows(tmp_path, row, message):
    with pytest.raises(ValueError, match=message):
        read_distribution(_csv(tmp_path, f"zone_id,resource,resource_level,probability\n{row}\n"))


def test_read_distribution_rejects_a_repeated_level(tmp_path):
    with pytest.raises(ValueError, match="only once"):
        read_distribution(_csv(tmp_path, "zone_id,resource,resource_level,probability\n1,grain,2,0.5\n1,grain,2,0.5\n"))


def test_read_distribution_needs_its_columns(tmp_path):
    with pytest.raises(ValueError, match="missing 'probability'"):
        read_distribution(_csv(tmp_path, "zone_id,resource,resource_level\n1,grain,2\n"))
    with pytest.raises(ValueError, match="at least one stratum"):
        read_distribution(_csv(tmp_path, "resource,resource_level,probability\ngrain,2,1\n"))


def _zones(tmp_path, ids, geometries, name="zones.gpkg"):
    path = str(tmp_path / name)
    geopandas.GeoDataFrame({"zone_id": ids}, geometry=geometries, crs="EPSG:28992").to_file(path, driver="GPKG")
    return path


def test_read_zones(tmp_path):
    zones = read_zones(_zones(tmp_path, [1, 2], [box(0, 0, 1, 1), box(2, 0, 3, 1)]))
    assert zones["zone_id"].tolist() == [1, 2]
    assert zones.crs.to_epsg() == 28992


def test_read_zones_missing_file(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        read_zones(str(tmp_path / "missing.gpkg"))


def test_read_zones_rejects_duplicate_ids(tmp_path):
    with pytest.raises(ValueError, match="unique"):
        read_zones(_zones(tmp_path, [1, 1], [box(0, 0, 1, 1), box(2, 0, 3, 1)]))


def test_read_zones_rejects_non_polygons(tmp_path):
    with pytest.raises(ValueError, match="polygons"):
        read_zones(_zones(tmp_path, [1], [Point(0, 0)]))


def test_read_zones_needs_a_zone_id(tmp_path):
    path = str(tmp_path / "zones.gpkg")
    geopandas.GeoDataFrame({"id": [1]}, geometry=[box(0, 0, 1, 1)], crs="EPSG:28992").to_file(path, driver="GPKG")
    with pytest.raises(ValueError, match="zone_id"):
        read_zones(path)


def test_read_zones_reports_an_unreadable_file(tmp_path):
    path = tmp_path / "zones.gpkg"
    path.write_text("not a geopackage")
    with pytest.raises(ValueError, match="zones.gpkg"):
        read_zones(str(path))
