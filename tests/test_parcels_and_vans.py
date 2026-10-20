import geopandas
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, box

from netsy.helpers.fratar import fratar
from netsy.synth.deliveries import _improve, _routes_savings, deliveries
from netsy.synth.parcel_demand import parcel_demand
from netsy.synth.trip_matrices import trip_matrices
from tests.fixtures import CRS

# Four zones on a line, 1 km and 1 minute apart; zone 4 is external.
ZONES = ["1", "2", "3", "4"]
STEPS = np.abs(np.subtract.outer(np.arange(4), np.arange(4))).astype(np.float32)
SKIMS = (ZONES, STEPS / 60, STEPS)


def _zones():
    return geopandas.GeoDataFrame(
        {"zone_id": [1, 2, 3, 4], "external": [0, 0, 0, 1], "x": [0, 1, 2, 3], "y": [0, 0, 0, 0]},
        geometry=[box(i, 0, i + 1, 1) for i in range(4)], crs=CRS,
    )


def _depots():
    return geopandas.GeoDataFrame(
        {"facility_id": ["a1", "a3", "b2"], "facility_type": ["parcel_depot"] * 3, "zone_id": [1, 3, 2],
         "operator": ["a", "a", "b"]},
        geometry=[Point(0, 0), Point(2, 0), Point(1, 0)], crs=CRS,
    )


def _csv(rows, columns):
    return pd.DataFrame(rows, columns=columns).astype(str).replace({"nan": np.nan, "None": np.nan})


def _demand(**overrides):
    tables = {
        "attributes": _csv([("1", 100), ("2", 0), ("3", 50)], ["zone_id", "jobs"]),
        "rates": _csv([("jobs", 0.1)], ["attribute", "rate"]),
        "population": _csv([("1", "young", 10), ("2", "young", 20), ("2", "old", 20)], ["zone_id", "age", "persons"]),
        "levels": _csv([(0, 0, 0.0), (1, 6, None)], ["level", "quantity", "threshold"]),
        "utility": _csv([("young", 50), ("old", -50)], ["age", "value"]),
        "shares": _csv([("a", 0.5), ("b", 0.5)], ["operator", "share"]),
        "settings": _csv([("period", 2)], ["setting", "value"]),
    }
    tables.update(overrides)
    return parcel_demand(_zones(), _depots(), SKIMS, *tables.values())


def test_parcels_are_linear_in_attributes_plus_an_ordered_logit_per_person():
    table = _demand()
    per_zone = table.groupby("destination_zone_id")["parcels"].sum()
    # Zone 1: 10 business + 10 young people ordering 6 per 2 days; zone 2:
    # 20 young (60) and 20 old (none); zone 3: 5 business, rounded per
    # operator as MASS-GT does, 2.5 to 2.
    assert per_zone.to_dict() == {1: 40, 2: 60, 3: 4}


def test_consumer_parcels_scale_to_a_number_per_person():
    settings = _csv([("period", 2), ("per_person", 0.5)], ["setting", "value"])
    total = _demand(settings=settings, attributes=_csv([("1", 0)], ["zone_id", "jobs"]))["parcels"].sum()
    assert total == pytest.approx(0.5 * 50, abs=2)


def test_each_operator_sends_from_its_nearest_depot():
    table = _demand()
    a = table[table["operator"] == "a"].set_index("destination_zone_id")["facility_id"].to_dict()
    assert a == {1: "a1", 2: "a1", 3: "a3"}
    assert set(table.loc[table["operator"] == "b", "facility_id"]) == {"b2"}


def _deliveries(rows, routing="massgt", max_load=4):
    demand = _csv(rows, ["destination_zone_id", "operator", "facility_id", "origin_zone_id", "parcels"])
    settings = _csv([("max_load", max_load), ("drop_time", 0.1)], ["setting", "value"])
    departures = _csv([(1, 0.0), (2, 1.0)], ["hour", "cumulative_share"])
    return deliveries(_zones(), SKIMS, demand, settings, departures, np.random.default_rng(0), routing)


@pytest.mark.parametrize("routing", ["massgt", "savings"])
def test_tours_deliver_every_parcel_within_the_load_and_return(routing):
    trips = _deliveries([(2, "a", "a1", 1, 3), (3, "a", "a1", 1, 2), (4, "a", "a1", 1, 9)], routing)
    assert trips["parcels"].sum() == 14
    for _, tour in trips.groupby("tour_id"):
        assert tour["origin_zone_id"].iloc[0] == 1 == tour["destination_zone_id"].iloc[-1]
        assert tour["quantity"].iloc[0] <= 4 and tour["parcels"].iloc[-1] == 0
        assert (tour["quantity"].diff().fillna(0) <= 0).all()
    # Full vans go straight to zone 4.
    assert ((trips["destination_zone_id"] == 4) & (trips["parcels"] == 4)).sum() == 2


def test_trips_depart_after_the_drop_time_of_the_stop_before():
    trips = _deliveries([(2, "a", "a1", 1, 1), (3, "a", "a1", 1, 1)])
    tour = trips[trips["tour_id"] == 1]
    first, second = tour.iloc[0], tour.iloc[1]
    assert first["departure"] >= 1 and first["departure"] < 2
    assert second["departure"] == pytest.approx(first["arrival"] + 0.1 * first["parcels"])


def test_savings_routes_are_no_longer_than_one_tour_per_stop():
    distance = np.abs(np.subtract.outer(np.arange(6), np.arange(6))).astype(float)
    routes = _routes_savings(0, [1, 2, 3, 4, 5], [1] * 5, 10, distance)
    assert routes == [[0, 1, 2, 3, 4, 5, 0]] or sum(distance[r[:-1], r[1:]].sum() for r in routes) == 10


def test_moving_single_stops_fixes_a_detour():
    distance = np.abs(np.subtract.outer(np.arange(5), np.arange(5))).astype(float)
    assert _improve([0, 3, 1, 2, 4, 0], distance) in ([0, 1, 2, 3, 4, 0], [0, 4, 3, 2, 1, 0])


def test_fratar_matches_rows_and_stops_at_the_tolerance():
    matrix, convergence = fratar(np.ones((2, 2)), np.array([3.0, 1.0]), np.array([2.0, 2.0]), 1e-6, 100)
    assert matrix.sum(axis=1) == pytest.approx([3, 1])
    assert matrix.sum(axis=0) == pytest.approx([2, 2], abs=1e-4)
    assert convergence <= 1e-6


def test_trip_matrices_balance_productions_by_gravity_and_drop_external_pairs():
    attributes = _csv([("1", 10), ("2", 10), ("3", 10), ("4", 10)], ["zone_id", "jobs"])
    rates = _csv([("service", "jobs", 1.0)], ["segment", "attribute", "rate"])
    decay = _csv([("service", 0.0, 2.0, 0.0, 1.0)], ["segment", "alpha", "beta", "cost_per_hour", "cost_per_km"])
    trips = trip_matrices(_zones(), SKIMS, attributes, rates, decay)["service"]
    assert trips[3, 3] == 0
    assert trips[:3].sum(axis=1) == pytest.approx([10, 10, 10], abs=0.01)
    assert trips[0, 1] > trips[0, 2]
