import geopandas
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from netsy.helpers.validate import check_size_classes, check_size_totals
from netsy.synth.agents import agents
from tests.fixtures import CRS


def _zones():
    return geopandas.GeoDataFrame({"zone_id": [1, 2]}, geometry=[box(0, 0, 1, 1), box(2, 0, 3, 1)], crs=CRS)


def _table(rows, columns, check):
    # As the readers return them: every cell text, then checked.
    return check(pd.DataFrame(rows, columns=columns).astype(str).replace("nan", np.nan))


def _inputs(**overrides):
    tables = {
        "size_totals": _table([("1", "shop", 30), ("2", "shop", 12), ("2", "farm", 7)], ["zone_id", "sector", "size"], check_size_totals),
        "size_classes": _table(
            [("shop", 1, 4, 0.5), ("shop", 5, 9, 0.5), ("farm", 2, 2, 1.0)],
            ["sector", "size_min", "size_max", "probability"], check_size_classes,
        ),
    }
    tables.update(overrides)
    return tables


def _synth(seed=0, min_size=0, **overrides):
    tables = _inputs(**overrides)
    return agents(_zones(), tables["size_totals"], tables["size_classes"], np.random.default_rng(seed), min_size)


def test_output_columns():
    table = _synth()
    assert list(table.columns) == ["agent_id", "zone_id", "sector", "size", "geometry"]
    assert table["agent_id"].tolist() == list(range(1, len(table) + 1))
    assert table.crs == CRS
    assert set(table.geometry.geom_type) == {"Point"}


@pytest.mark.parametrize("seed", range(10))
def test_sizes_use_up_each_stratum_total_overshooting_by_at_most_30_percent_of_what_was_left(seed):
    table = _synth(seed)
    for (zone, sector), total in {("1", "shop"): 30, ("2", "farm"): 7, ("2", "shop"): 12}.items():
        sizes = table[(table["zone_id"] == zone) & (table["sector"] == sector)]["size"].tolist()
        left_before_last = total - sum(sizes[:-1])
        assert sum(sizes[:-1]) < total <= sum(sizes)
        assert sizes[-1] <= 1.3 * left_before_last


@pytest.mark.parametrize("seed", range(10))
def test_sizes_come_from_their_class_bounds(seed):
    table = _synth(seed)
    shops = table[table["sector"] == "shop"]
    # Every size is within the class bounds except a stratum's last agent,
    # which takes what is left.
    assert ((shops["size"] >= 1) & (shops["size"] <= 9)).all()
    farms = table[table["sector"] == "farm"]
    assert farms["size"].tolist() == [2, 2, 2, 1]


def test_classes_keyed_by_a_subset_of_strata_apply_in_every_zone():
    table = _synth()
    assert set(table.loc[table["sector"] == "shop", "zone_id"]) == {"1", "2"}


def test_seed_repeats_the_same_agents():
    a, b = _synth(seed=3), _synth(seed=3)
    pd.testing.assert_frame_equal(pd.DataFrame(a.drop(columns="geometry")), pd.DataFrame(b.drop(columns="geometry")))
    assert a.geometry.equals(b.geometry)


def test_agents_are_placed_in_their_zone():
    table = _synth()
    zones = _zones().set_index(_zones()["zone_id"].astype(str))
    assert all(zones.loc[zone, "geometry"].contains(point) for zone, point in zip(table["zone_id"], table.geometry))


def test_a_stratum_without_classes_is_an_error():
    classes = _table([("shop", 1, 4, 1.0)], ["sector", "size_min", "size_max", "probability"], check_size_classes)
    with pytest.raises(ValueError, match="no size classes for {'sector': 'farm'}"):
        _synth(size_classes=classes)


def test_key_columns_must_be_stratum_columns():
    classes = _table([("north", 1, 4, 1.0)], ["region", "size_min", "size_max", "probability"], check_size_classes)
    with pytest.raises(ValueError, match=r"size_classes.csv: columns \['region'\] are not stratum columns"):
        _synth(size_classes=classes)


def test_a_zone_missing_from_the_zones_is_an_error():
    totals = _table([("9", "shop", 5)], ["zone_id", "sector", "size"], check_size_totals)
    with pytest.raises(ValueError, match=r"zones \['9'\] are not in zones.gpkg"):
        _synth(size_totals=totals)


@pytest.mark.parametrize("rows, message", [
    ([("shop", -1, 4, 1.0)], "'size_min' must hold whole numbers of at least 0"),
    ([("shop", 0, 0, 1.0)], "needs a class that can draw a size above zero"),
    ([("shop", 5, 4, 1.0)], "'size_max' must be at least 'size_min'"),
    ([("shop", 1, 4, 0.4)], "must sum to one"),
])
def test_size_classes_are_checked(rows, message):
    with pytest.raises(ValueError, match=message):
        _table(rows, ["sector", "size_min", "size_max", "probability"], check_size_classes)


def test_size_totals_need_a_zone():
    with pytest.raises(ValueError, match="missing 'zone_id' column"):
        _table([("shop", 5)], ["sector", "size"], check_size_totals)


def _classes(rows, columns=("sector", "size_min", "size_max", "probability")):
    return _table(rows, list(columns), check_size_classes)


@pytest.mark.parametrize("seed", range(10))
def test_an_open_class_draws_a_triangle_that_follows_what_is_left(seed):
    totals = _table([("1", "shop", 1000)], ["zone_id", "sector", "size"], check_size_totals)
    classes = _classes([("shop", 100, None, 150, 1.0)], ("sector", "size_min", "size_max", "size_median", "probability"))
    sizes = _synth(seed, size_totals=totals, size_classes=classes)["size"].tolist()
    left = 1000.0
    for size in sizes[:-1]:
        # Between the class minimum and max(median, 1.5 x what was left).
        assert 100 <= size <= max(150, 1.5 * left)
        left -= size
    assert sizes[-1] <= 1.3 * left


def test_an_open_class_needs_a_median():
    with pytest.raises(ValueError, match="needs a 'size_median' column"):
        _classes([("shop", 100, None, 1.0)])
    with pytest.raises(ValueError, match="needs a 'size_median' above its 'size_min'"):
        _classes([("shop", 100, None, 50, 1.0)], ("sector", "size_min", "size_max", "size_median", "probability"))


def test_a_draw_far_above_what_is_left_takes_exactly_what_is_left():
    totals = _table([("1", "shop", 10)], ["zone_id", "sector", "size"], check_size_totals)
    classes = _classes([("shop", 40, 40, 1.0)])
    assert _synth(size_totals=totals, size_classes=classes)["size"].tolist() == [10]


def test_a_draw_at_most_30_percent_above_what_is_left_is_kept():
    totals = _table([("1", "shop", 10)], ["zone_id", "sector", "size"], check_size_totals)
    classes = _classes([("shop", 13, 13, 1.0)])
    assert _synth(size_totals=totals, size_classes=classes)["size"].tolist() == [13]


def test_agents_of_size_zero_are_not_agents():
    classes = _classes([("shop", 0, 1, 1.0), ("farm", 2, 2, 1.0)])
    table = _synth(size_classes=classes)
    assert (table["size"] > 0).all()


def test_agents_below_the_minimum_size_are_dropped_and_their_size_is_not_given_to_others():
    everyone, kept = _synth(seed=4), _synth(seed=4, min_size=5)
    assert (kept["size"] >= 5).all()
    assert "farm" not in set(kept["sector"])
    assert kept["size"].sum() == everyone.loc[everyone["size"] >= 5, "size"].sum()

