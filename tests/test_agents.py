import geopandas
import numpy as np
import pytest

from netsy.synth.agents import agents
from tests.agent_fixtures import CRS, aggregate, distribution, zones

COLUMNS = ["zone_id", "sector", "grain", "parcels"]


def _synth(supply_rows, demand_rows, capacity_rows, need_rows, seed=0):
    return agents(
        aggregate(supply_rows, COLUMNS), aggregate(demand_rows, COLUMNS),
        distribution(capacity_rows), distribution(need_rows), zones(),
        np.random.default_rng(seed),
    )


def _plain(seed=0):
    """Zone 1: grain only, capacity 0 or 2, need always 2. Zone 2: grain and
    parcels, always capacity 2 / need 2 and capacity 1 / need 1."""
    return _synth(
        [("1", "a", "4", None), ("2", "a", "6", "3")],
        [("1", "a", "4", None), ("2", "a", "6", "3")],
        [(1, "a", "grain", 0, 0.5), (1, "a", "grain", 2, 0.5), (2, "a", "grain", 2, 1.0), (2, "a", "parcels", 1, 1.0)],
        [(1, "a", "grain", 2, 1.0), (2, "a", "grain", 2, 1.0), (2, "a", "parcels", 1, 1.0)],
        seed,
    )


def test_output_columns_and_types():
    table = _plain()
    assert list(table.columns) == [
        "agent_id", "zone_id", "sector", "grain_capacity", "grain_need", "parcels_capacity", "parcels_need", "geometry",
    ]
    assert table["agent_id"].tolist() == list(range(1, len(table) + 1))
    assert str(table["grain_capacity"].dtype) == "Int64"
    assert table.crs == CRS
    assert set(table.geometry.geom_type) == {"Point"}


def test_agent_count_is_where_depletion_stops():
    table = _plain()
    assert (table["zone_id"] == 1).sum() == 2
    assert (table["zone_id"] == 2).sum() == 3


def test_a_resource_a_stratum_lacks_is_empty_not_zero():
    table = _plain()
    zone_1 = table[table["zone_id"] == 1]
    assert zone_1["parcels_capacity"].isna().all() and zone_1["parcels_need"].isna().all()
    zone_2 = table[table["zone_id"] == 2]
    assert zone_2["parcels_capacity"].tolist() == [1, 1, 1]


@pytest.mark.parametrize("seed", range(10))
def test_agents_never_exceed_the_supply_or_demand(seed):
    table = _plain(seed)
    for zone, supply, demand in ((1, 4, 4), (2, 6, 6)):
        rows = table[table["zone_id"] == zone]
        assert rows["grain_capacity"].sum() <= supply
        assert rows["grain_need"].sum() <= demand
    assert table[table["zone_id"] == 2]["grain_need"].sum() == 6


def test_agents_are_placed_inside_their_zone():
    table = _plain()
    polygons = zones().set_index("zone_id").geometry
    assert all(polygons[zone].contains(point) for zone, point in zip(table["zone_id"], table.geometry))


def test_same_seed_same_agents_different_seed_different_agents():
    first, second, other = _plain(3), _plain(3), _plain(4)
    assert first["grain_capacity"].tolist() == second["grain_capacity"].tolist()
    assert first.geometry.to_wkt().tolist() == second.geometry.to_wkt().tolist()
    assert first.geometry.to_wkt().tolist() != other.geometry.to_wkt().tolist()


def test_an_agent_with_nothing_to_draw_is_kept_and_generation_stops():
    table = _synth(
        [("1", "a", "0", "0")], [("1", "a", "0", "0")],
        [(1, "a", "grain", 0, 1.0), (1, "a", "parcels", 0, 1.0)],
        [(1, "a", "grain", 0, 1.0), (1, "a", "parcels", 0, 1.0)],
    )
    assert len(table) == 1
    assert table.loc[0, ["grain_capacity", "grain_need", "parcels_capacity", "parcels_need"]].tolist() == [0, 0, 0, 0]


def test_one_infeasible_resource_stops_the_whole_stratum():
    # parcels capacity is always 5 but only 3 are supplied, so no complete
    # agent exists even though grain could be drawn.
    with pytest.raises(ValueError, match="no agents"):
        _synth(
            [("1", "a", "4", "3")], [("1", "a", "4", "3")],
            [(1, "a", "grain", 2, 1.0), (1, "a", "parcels", 5, 1.0)],
            [(1, "a", "grain", 2, 1.0), (1, "a", "parcels", 1, 1.0)],
        )


def test_generation_stops_after_the_last_agent_that_fits():
    table = _synth(
        [("1", "a", "5", "0")], [("1", "a", "5", "0")],
        [(1, "a", "grain", 2, 1.0), (1, "a", "parcels", 0, 1.0)],
        [(1, "a", "grain", 2, 1.0), (1, "a", "parcels", 0, 1.0)],
    )
    assert len(table) == 2
    assert table["grain_capacity"].sum() == 4


def test_no_usable_strata_is_an_error():
    with pytest.warns(UserWarning), pytest.raises(ValueError, match="no agents"):
        _synth(
            [("9", "a", "4", None)], [("9", "a", "4", None)],
            [(9, "a", "grain", 2, 1.0)], [(9, "a", "grain", 2, 1.0)],
        )


def test_crs_follows_the_zones():
    table = _plain()
    assert isinstance(table, geopandas.GeoDataFrame)
    assert table.crs.to_epsg() == 28992
