import geopandas
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, box

from netsy.helpers import validate
from netsy.synth.shipments import _intrazonal, shipments
from tests.fixtures import CRS

# Zones 1 and 2 make up region "in", next to each other; zone 3 is also in
# "in" but far away; zone 9 is region "out".
ZONES = ["1", "2", "3", "9"]
DISTANCE = np.array([
    [1, 2, 50, 100],
    [2, 1, 50, 100],
    [50, 50, 1, 100],
    [100, 100, 100, 1],
], dtype=np.float32)


def _zones():
    return geopandas.GeoDataFrame(
        {"zone_id": [1, 2, 3, 9], "region": ["in", "in", "in", "out"], "density": [1.0, 2.0, 3.0, 0.0]},
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1), box(50, 0, 51, 1), box(100, 0, 101, 1)],
        crs=CRS,
    )


def _agents():
    return validate.check_agents(geopandas.GeoDataFrame(
        {"agent_id": [1, 2, 3, 4], "zone_id": [1, 2, 3, 3], "sector": ["farm", "shop", "shop", "farm"], "size": [10.0, 5.0, 5.0, 10.0]},
        geometry=[Point(0.5, 0.5), Point(1.5, 0.5), Point(50.5, 0.5), Point(50.6, 0.5)],
        crs=CRS,
    ))


def _facilities():
    return geopandas.GeoDataFrame(
        {
            "facility_id": ["dc", "a1", "a2", "b1"], "facility_type": ["dc", "depot", "depot", "depot"],
            "zone_id": [2, 1, 2, 3], "size": [1.0, 1.0, 1.0, 1.0], "operator": [None, "a", "a", "b"],
        },
        geometry=[Point(1.2, 0.2), Point(0.2, 0.2), Point(1.8, 0.8), Point(50.2, 0.2)],
        crs=CRS,
    )


def _table(rows, columns, check):
    # As the readers return them: every cell text, then checked.
    return check(pd.DataFrame(rows, columns=columns).astype(str).replace({"nan": np.nan, "None": np.nan}))


def _inputs(**overrides):
    tables = {
        "zones": _zones(),
        "agents": _agents(),
        "facilities": _facilities(),
        "skims": (list(ZONES), DISTANCE / 50, DISTANCE.copy()),
        "production_rates": _table([("farm", "grain", 1.0)], ["sector", "resource", "rate"], validate.check_rates),
        "consumption_rates": _table([("shop", "grain", 1.0)], ["sector", "resource", "rate"], validate.check_rates),
        "shipment_totals": _table(
            [("in", "in", "direct", "grain", 10.0)],
            ["origin_region", "destination_region", "flow_type", "resource", "quantity"], validate.check_shipment_totals,
        ),
        "flow_types": _table(
            [("direct", "agent", "agent", "origin"), ("export", "agent", "zone", "origin"), ("import", "zone", "agent", "destination"),
             ("to_dc", "agent", "dc", "origin"), ("fixed", "zone", "zone", None)],
            ["flow_type", "origin", "destination", "decay"], validate.check_flow_types,
        ),
        "distance_decay": _table([(-1.0, 1.0, 0.0, 1.0)], ["alpha", "beta", "cost_per_hour", "cost_per_km"], validate.check_distance_decay),
        "shipment_sizes": _table([("small", 1.0), ("large", 4.0)], ["size_class", "quantity"], validate.check_shipment_sizes),
        "shipment_vehicles": _table(
            [("van", 2.0, 0.0, 1.0), ("truck", 10.0, 0.0, 2.0)],
            ["vehicle", "capacity", "cost_per_hour", "cost_per_km"], validate.check_shipment_vehicles,
        ),
        "vehicle_choice": _table([(None, "constant", 0.0)], ["vehicle", "term", "value"], lambda t: validate.check_choice(t, "vehicle")),
        "delivery_windows": _table([("night", 0, 8), ("day", 8, 24)], ["window", "start", "end"], validate.check_delivery_windows),
        "delivery_choice": _table([(None, "constant", 0.0)], ["window", "term", "value"], lambda t: validate.check_choice(t, "window")),
    }
    tables.update(overrides)
    return tables


def _synth(seed=0, **overrides):
    return shipments(**_inputs(**overrides), rng=np.random.default_rng(seed))


def _totals(rows, columns=("origin_region", "destination_region", "flow_type", "resource", "quantity")):
    return _table(rows, list(columns), validate.check_shipment_totals)


def _choice(rows, alternative="vehicle"):
    return _table(rows, [alternative, "term", "value"], lambda t: validate.check_choice(t, alternative))


def test_output_columns():
    table = _synth()
    assert list(table.columns) == [
        "transaction_id", "resource", "quantity", "origin_agent_id", "destination_agent_id", "flow_type",
        "origin_facility_id", "destination_facility_id", "origin_zone_id", "destination_zone_id",
        "size_class", "vehicle", "window", "window_start", "window_end", "geometry",
    ]
    assert table["transaction_id"].tolist() == list(range(1, len(table) + 1))
    assert table.crs == CRS
    assert set(table.geometry.geom_type) == {"LineString"}


@pytest.mark.parametrize("seed", range(5))
def test_shipments_carry_their_class_quantity_until_the_total_is_moved(seed):
    table = _synth(seed)
    assert table["quantity"].sum() == pytest.approx(10.0)
    sizes = table["size_class"].map({"small": 1.0, "large": 4.0})
    assert (table["quantity"].iloc[:-1] == sizes.iloc[:-1]).all()
    assert 0 < table["quantity"].iloc[-1] <= sizes.iloc[-1]


@pytest.mark.parametrize("seed", range(5))
def test_senders_produce_and_receivers_consume_the_resource(seed):
    table = _synth(seed)
    assert set(table["origin_agent_id"]) <= {1, 4}
    assert set(table["destination_agent_id"]) <= {2, 3}
    lines = dict(zip(_agents()["agent_id"], _agents().geometry))
    for row in table.itertuples():
        assert row.geometry.coords[0] == lines[row.origin_agent_id].coords[0]
        assert row.geometry.coords[-1] == lines[row.destination_agent_id].coords[0]


def test_rates_keyed_by_a_shipment_stratum_apply_to_it():
    totals = _totals(
        [("in", "in", "direct", "grain", "bulk", 10.0)],
        ("origin_region", "destination_region", "flow_type", "resource", "segment", "quantity"),
    )
    rates = _table([("farm", "grain", "bulk", 1.0), ("shop", "grain", "parcel", 1.0)], ["sector", "resource", "segment", "rate"], validate.check_rates)
    table = _synth(shipment_totals=totals, production_rates=rates)
    assert set(table["origin_agent_id"]) <= {1, 4}
    assert set(table["segment"]) == {"bulk"}


def test_the_decayed_origin_is_drawn_near_the_destination():
    # A steep decay: from agent 2's zone, the farm next door is far cheaper
    # than the one 50 km away.
    decay = _table([(-10.0, 8.0, 0.0, 1.0)], ["alpha", "beta", "cost_per_hour", "cost_per_km"], validate.check_distance_decay)
    rates = _table([("shop", "grain", 1.0)], ["sector", "resource", "rate"], validate.check_rates)
    consumers = validate.check_agents(_agents().assign(sector=["farm", "shop", "farm", "farm"]))
    table = _synth(distance_decay=decay, consumption_rates=rates, agents=consumers,
                   shipment_totals=_totals([("in", "in", "direct", "grain", 200.0)]))
    assert (table["destination_agent_id"] == 2).all()
    assert (table["origin_agent_id"] == 1).mean() > 0.95


def test_without_decay_the_origin_is_drawn_by_weight_alone():
    decay = _table([(-10.0, 8.0, 0.0, 1.0)], ["alpha", "beta", "cost_per_hour", "cost_per_km"], validate.check_distance_decay)
    flows = _table([("direct", "agent", "agent", None)], ["flow_type", "origin", "destination", "decay"], validate.check_flow_types)
    table = _synth(distance_decay=decay, flow_types=flows, shipment_totals=_totals([("in", "in", "direct", "grain", 400.0)]))
    assert 0.3 < (table["origin_agent_id"] == 1).mean() < 0.7


def test_a_zone_end_is_the_zone_of_its_region():
    totals = _totals([("in", "out", "export", "grain", 5.0), ("out", "in", "import", "grain", 5.0)])
    table = _synth(shipment_totals=totals)
    exports, imports = table[table["flow_type"] == "export"], table[table["flow_type"] == "import"]
    assert (exports["destination_zone_id"] == 9).all() and exports["destination_agent_id"].isna().all()
    assert (imports["origin_zone_id"] == 9).all() and set(imports["destination_agent_id"]) <= {2, 3}
    assert exports["quantity"].sum() == pytest.approx(5.0) and imports["quantity"].sum() == pytest.approx(5.0)


def test_pinned_zones_restrict_their_end():
    totals = _totals(
        [("in", "in", "fixed", "grain", "1", "3", 3.0), ("in", "in", "direct", "grain", "3", None, 3.0)],
        ("origin_region", "destination_region", "flow_type", "resource", "origin_zone_id", "destination_zone_id", "quantity"),
    )
    table = _synth(shipment_totals=totals)
    fixed, direct = table[table["flow_type"] == "fixed"], table[table["flow_type"] == "direct"]
    assert (fixed["origin_zone_id"] == 1).all() and (fixed["destination_zone_id"] == 3).all()
    assert (direct["origin_agent_id"] == 4).all()


def test_a_pinned_zone_must_be_in_its_region():
    totals = _totals(
        [("in", "in", "fixed", "grain", "9", "3", 3.0)],
        ("origin_region", "destination_region", "flow_type", "resource", "origin_zone_id", "destination_zone_id", "quantity"),
    )
    with pytest.raises(ValueError, match="zone '9' is not in origin region 'in'"):
        _synth(shipment_totals=totals)


def test_facility_ends_are_drawn_by_their_weight_column():
    facilities = _facilities().assign(size=[1.0, 0.0, 0.0, 0.0])
    table = _synth(facilities=facilities, shipment_totals=_totals([("in", "in", "to_dc", "grain", 5.0)]))
    assert (table["destination_facility_id"] == "dc").all() and table["destination_agent_id"].isna().all()
    assert (table["destination_zone_id"] == 2).all()


def test_same_and_distinct_ends_share_an_operator_but_differ():
    flows = _table(
        [("depots", "depot", "depot", None, "operator", "true")],
        ["flow_type", "origin", "destination", "decay", "same", "distinct"], validate.check_flow_types,
    )
    facilities = _facilities().assign(size=[1.0, 1.0, 1.0, 0.0])
    table = _synth(flow_types=flows, facilities=facilities, shipment_totals=_totals([("in", "in", "depots", "grain", 40.0)]))
    pairs = set(zip(table["origin_facility_id"], table["destination_facility_id"]))
    assert pairs <= {("a1", "a2"), ("a2", "a1")} and len(pairs) == 2


def test_an_end_with_no_one_to_pair_with_is_an_error():
    flows = _table(
        [("depots", "depot", "depot", None, "operator", "true")],
        ["flow_type", "origin", "destination", "decay", "same", "distinct"], validate.check_flow_types,
    )
    facilities = _facilities().assign(size=[1.0, 1.0, 0.0, 1.0], zone_id=[2, 1, 2, 3])
    with pytest.raises(ValueError, match="no 'depot' origin can be paired by flow type 'depots'"):
        _synth(flow_types=flows, facilities=facilities, shipment_totals=_totals([("in", "in", "depots", "grain", 40.0)]))


def test_a_weight_column_names_the_facility_weight():
    flows = _table(
        [("to_dc", "agent", "depot", "origin", "busy")],
        ["flow_type", "origin", "destination", "decay", "destination_weight"], validate.check_flow_types,
    )
    facilities = _facilities().assign(busy=[0.0, 0.0, 1.0, 0.0])
    table = _synth(flow_types=flows, facilities=facilities, shipment_totals=_totals([("in", "in", "to_dc", "grain", 5.0)]))
    assert (table["destination_facility_id"] == "a2").all()


@pytest.mark.parametrize("rows, vehicle, size_class", [
    ([("truck", "constant", 20.0)], "truck", None),
    ([(None, "size", 20.0)], None, "large"),
    ([(None, "size", -20.0)], None, "small"),
    ([(None, "transport_cost", -50.0)], "van", "small"),
    ([("truck", "destination:agent", 20.0)], "truck", None),
    ([("truck", "destination:dc", 20.0)], None, None),
    ([("truck", "distance_above:0.5", 20.0)], "truck", None),
    ([("truck", "size_class:large", 20.0)], "truck", "large"),
])
def test_size_class_and_vehicle_follow_the_choice_coefficients(rows, vehicle, size_class):
    table = _synth(vehicle_choice=_choice(rows), shipment_totals=_totals([("in", "in", "direct", "grain", 100.0)]))
    if vehicle:
        assert (table["vehicle"] == vehicle).mean() > 0.95
    else:
        assert table["vehicle"].nunique() > 1 or size_class
    if size_class:
        assert (table["size_class"].iloc[:-1] == size_class).mean() > 0.95


def test_an_unknown_choice_term_is_an_error():
    with pytest.raises(ValueError, match="vehicle_choice.csv: unknown term 'speed'"):
        _synth(vehicle_choice=_choice([(None, "speed", 1.0)]))


def test_a_stratum_without_choice_coefficients_is_an_error():
    choice = _table([("salt", None, "constant", 0.0)], ["resource", "vehicle", "term", "value"], lambda t: validate.check_choice(t, "vehicle"))
    with pytest.raises(ValueError, match=r"vehicle_choice.csv: no coefficients for \{'resource': 'grain'\}"):
        _synth(vehicle_choice=choice)


@pytest.mark.parametrize("rows, window", [
    ([("day", "constant", 20.0)], "day"),
    ([("night", "vehicle:van", 20.0)], "night"),
    ([("night", "destination:density", 20.0)], "night"),
    ([(None, "log_duration", 20.0)], "day"),
])
def test_delivery_windows_follow_the_choice_coefficients(rows, window):
    table = _synth(delivery_choice=_choice(rows, "window"), vehicle_choice=_choice([("van", "constant", 20.0)]))
    assert (table["window"] == window).all()
    bounds = {"night": (0, 8), "day": (8, 24)}[window]
    assert (table["window_start"] == bounds[0]).all() and (table["window_end"] == bounds[1]).all()


def test_delivery_windows_are_optional_as_a_pair():
    table = _synth(delivery_windows=None, delivery_choice=None)
    assert "window" not in table.columns
    with pytest.raises(ValueError, match="give both, or neither"):
        _synth(delivery_windows=None)


def test_seed_repeats_the_same_shipments():
    a, b = _synth(seed=3), _synth(seed=3)
    pd.testing.assert_frame_equal(pd.DataFrame(a.drop(columns="geometry")), pd.DataFrame(b.drop(columns="geometry")))


@pytest.mark.parametrize("overrides, message", [
    ({"zones": _zones().drop(columns="region")}, "zones.gpkg: missing 'region' column"),
    ({"skims": (["1", "2", "3"], DISTANCE[:3, :3], DISTANCE[:3, :3])}, r"zones \['9'\] of zones.gpkg are not in the skims"),
    ({"shipment_totals": _totals([("in", "in", "teleport", "grain", 1.0)])}, "flow type 'teleport' is not in flow_types.csv"),
    ({"shipment_totals": _totals([("in", "moon", "direct", "grain", 1.0)])}, "must be regions of zones.gpkg"),
    ({"shipment_totals": _totals([("in", "in", "direct", "salt", 1.0)])}, "production_rates.csv: no agent in origin region 'in'"),
    ({"facilities": None, "shipment_totals": _totals([("in", "in", "to_dc", "grain", 1.0)])}, "facility type 'dc' needs facilities.gpkg"),
    ({"production_rates": _table([("north", "grain", 1.0)], ["region", "resource", "rate"], validate.check_rates)},
     r"production_rates.csv: columns \['region'\] are not agent or shipment stratum columns"),
])
def test_inputs_that_do_not_fit_together_are_errors(overrides, message):
    with pytest.raises(ValueError, match=message):
        _synth(**overrides)


def test_zero_skims_take_half_the_smallest_positive_value_of_their_row():
    matrix = np.array([[0, 4, 6], [3, 0, -1], [0, 0, 0]], dtype=np.float32)
    assert _intrazonal(matrix).tolist() == [[2, 4, 6], [3, 1.5, 1.5], [0, 0, 0]]


@pytest.mark.parametrize("check, rows, columns, message", [
    (validate.check_flow_types, [("x", "agent", "agent", "both")], ["flow_type", "origin", "destination", "decay"], "'decay' must be"),
    (validate.check_shipment_sizes, [("small", 0)], ["size_class", "quantity"], "'quantity' must hold numbers above 0"),
    (validate.check_delivery_windows, [("day", 8, 8)], ["window", "start", "end"], "must end after it starts"),
    (validate.check_rates, [("farm", -1)], ["sector", "rate"], "'rate' must hold numbers of at least 0"),
    (validate.check_shipment_totals, [("in", "in", "direct", 1.0)], ["origin_region", "destination_region", "flow_type", "quantity"], r"missing columns \['resource'\]"),
])
def test_tables_are_checked(check, rows, columns, message):
    with pytest.raises(ValueError, match=message):
        _table(rows, columns, check)
