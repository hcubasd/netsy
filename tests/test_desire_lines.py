import geopandas
import numpy as np
from shapely.geometry import Point

from netsy.synth.desire_lines import desire_lines
from tests.agent_fixtures import CRS


def _agents(rows):
    return geopandas.GeoDataFrame(rows, crs=CRS)


def test_provider_is_matched_until_its_capacity_is_depleted():
    table = desire_lines(
        _agents([
            {"agent_id": 1, "grain_capacity": 4, "grain_need": 0, "geometry": Point(0, 0)},
            {"agent_id": 2, "grain_capacity": 0, "grain_need": 2, "geometry": Point(1, 0)},
            {"agent_id": 3, "grain_capacity": 0, "grain_need": 2, "geometry": Point(2, 0)},
        ]),
        np.random.default_rng(1),
    )
    assert table["origin_agent_id"].tolist() == [1, 1]
    assert sorted(table["quantity"]) == [2, 2]


def test_line_direction_and_totals_follow_provider_and_consumer():
    table = desire_lines(
        _agents([
            {"agent_id": 1, "grain_capacity": 8, "grain_need": 0, "geometry": Point(0, 0)},
            {"agent_id": 2, "grain_capacity": 0, "grain_need": 5, "geometry": Point(1, 0)},
        ]),
        np.random.default_rng(1),
    )
    assert list(table.columns) == ["resource", "quantity", "origin_agent_id", "geometry"]
    assert table.crs == CRS
    assert table["quantity"].sum() == 5
    assert table["origin_agent_id"].tolist() == [1]
    assert list(table.geometry.iloc[0].coords) == [(0, 0), (1, 0)]


def test_resources_with_missing_agent_values_only_use_participating_agents():
    table = desire_lines(
        _agents([
            {"agent_id": 1, "grain_capacity": 3, "grain_need": 0, "parcel_capacity": np.nan, "parcel_need": np.nan, "geometry": Point(0, 0)},
            {"agent_id": 2, "grain_capacity": 0, "grain_need": 3, "parcel_capacity": np.nan, "parcel_need": np.nan, "geometry": Point(1, 0)},
            {"agent_id": 3, "grain_capacity": np.nan, "grain_need": np.nan, "parcel_capacity": 2, "parcel_need": 0, "geometry": Point(2, 0)},
            {"agent_id": 4, "grain_capacity": np.nan, "grain_need": np.nan, "parcel_capacity": 0, "parcel_need": 2, "geometry": Point(3, 0)},
        ]),
        np.random.default_rng(1),
    )
    assert dict(table.groupby("resource")["quantity"].sum()) == {"grain": 3, "parcel": 2}


def test_an_agent_cannot_trade_with_itself():
    table = desire_lines(
        _agents([{"agent_id": 1, "grain_capacity": 4, "grain_need": 4, "geometry": Point(0, 0)}]),
        np.random.default_rng(1),
    )
    assert table.empty


def test_seed_repeats_the_same_matching():
    agents = _agents([
        {"agent_id": 1, "grain_capacity": 4, "grain_need": 0, "geometry": Point(0, 0)},
        {"agent_id": 2, "grain_capacity": 0, "grain_need": 2, "geometry": Point(1, 0)},
        {"agent_id": 3, "grain_capacity": 0, "grain_need": 2, "geometry": Point(2, 0)},
    ])
    first = desire_lines(agents, np.random.default_rng(3))
    second = desire_lines(agents, np.random.default_rng(3))
    assert first.equals(second)
