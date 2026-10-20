import geopandas
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, box

from netsy.synth.network_emissions import _hot_emission_factor, emissions_by_copert, emissions_by_factors
from netsy.synth.network_loads import network_loads
from tests.fixtures import CRS

# Nodes 1-2-3 on a line, a fast bypass 1-4-3, and a connector to zone 9's node 5.


def _network():
    links = [
        ("ab", 1, 2, 1.0, "street"), ("bc", 2, 3, 1.0, "street"), ("ad", 1, 4, 1.5, "motorway"),
        ("dc", 4, 3, 1.5, "motorway"), ("ba", 2, 1, 1.0, "street"), ("cb", 3, 2, 1.0, "street"),
        ("ce", 3, 5, 0.1, "connector"), ("ec", 5, 3, 0.1, "connector"),
    ]
    return geopandas.GeoDataFrame(
        [{"link_id": i, "from_node": a, "to_node": b, "length": l, "road_type": t} for i, a, b, l, t in links],
        geometry=[LineString([(0, 0), (1, 1)])] * len(links), crs=CRS,
    )


def _zones():
    return geopandas.GeoDataFrame({"zone_id": [1, 3, 9], "node": [1, 3, 5]}, geometry=[box(0, 0, 1, 1)] * 3, crs=CRS)


def _csv(rows, columns):
    return pd.DataFrame(rows, columns=columns).astype(str).replace({"nan": np.nan, "None": np.nan})


def _speeds(street=10.0, motorway=100.0):
    rows = []
    for link in _network().itertuples():
        for speed_class in ("truck", "van"):
            rows.append((link.link_id, speed_class, street if link.road_type == "street" else motorway))
    return _csv(rows, ["link_id", "speed_class", "speed"])


def _loads(trips, speeds=None, road_costs=None, matrices=None, assignment=None):
    vehicles = _csv([("lorry", "truck", 10, 1), ("van", "van", 0, 1)], ["vehicle", "speed_class", "cost_per_hour", "cost_per_km"])
    intervals = _csv([("night", 0, 6), ("day", 6, 24)], ["time_interval", "start", "end"])
    road_costs = road_costs if road_costs is not None else _csv([], ["road_type", "speed_class", "cost"])
    return network_loads(
        _network(), _zones(), vehicles, speeds if speeds is not None else _speeds(), road_costs, intervals,
        {"tours.gpkg": trips} if trips is not None else {}, matrices, assignment,
    )


def _trips(rows):
    return pd.DataFrame(rows, columns=["departure", "vehicle", "utilization", "origin_zone_id", "destination_zone_id", "segment"])


def test_a_trip_takes_the_cheapest_path_by_time_and_distance():
    loads = _loads(_trips([(7.5, "lorry", 0.5, 1, 3, "food")]))
    # The lorry pays for time, so the fast bypass wins; the van pays only
    # for kilometres, so the shorter street does.
    assert set(loads["link_id"]) == {"ad", "dc"}
    assert loads["time_interval"].tolist() == ["day", "day"] and loads["utilization"].tolist() == [0.5, 0.5]
    vans = _loads(_trips([(1.0, "van", 0.0, 1, 3, "parcels")]))
    assert set(vans["link_id"]) == {"ab", "bc"} and set(vans["time_interval"]) == {"night"}


def test_road_costs_fix_the_cost_of_a_road_type_for_a_class():
    costs = _csv([("motorway", "truck", 1000)], ["road_type", "speed_class", "cost"])
    assert set(_loads(_trips([(7.5, "lorry", 0.5, 1, 3, "food")]), road_costs=costs)["link_id"]) == {"ab", "bc"}


def test_loads_sum_trips_and_average_utilization_per_group():
    loads = _loads(_trips([(7, "lorry", 0.2, 1, 9, "food"), (8, "lorry", 0.6, 1, 9, "food"), (25, "lorry", 1.0, 1, 3, "food")]))
    ad = loads[loads["link_id"] == "ad"].set_index("time_interval")
    assert ad.loc["day", "trips"] == 2 and ad.loc["day", "utilization"] == pytest.approx(0.4)
    # A departure past the period's end wraps around: 25 h is 1 h, at night.
    assert ad.loc["night", "trips"] == 1
    assert loads.loc[loads["link_id"] == "ce", "trips"].sum() == 2
    assert loads.loc[loads["link_id"] == "ad", "speed"].unique().tolist() == [100.0]


def test_matrix_trips_load_without_an_interval_above_their_minimum():
    matrix = np.array([[0, 2.5, 0.05], [0, 0, 0], [0, 0, 0]], dtype=np.float32)
    assignment = _csv([("service", "van", "van_service", 0.5, 0.1)], ["matrix", "vehicle", "segment", "utilization", "minimum"])
    loads = _loads(None, matrices=(["1", "3", "9"], {"service": matrix}), assignment=assignment)
    assert set(loads["link_id"]) == {"ab", "bc"} and loads["trips"].tolist() == [2.5, 2.5]
    assert loads["time_interval"].tolist() == ["", ""] and loads["segment"].unique().tolist() == ["van_service"]


def test_speeds_must_cover_every_link():
    with pytest.raises(ValueError, match="needs a speed on every link"):
        _loads(_trips([(7, "lorry", 0.5, 1, 3, "food")]), speeds=_speeds().iloc[2:])


def _load_rows():
    return pd.DataFrame({
        "link_id": ["ab", "ad"], "time_interval": ["day", "day"], "vehicle": ["lorry", "lorry"], "segment": ["food", "food"],
        "trips": [2, 1], "utilization": [0.5, 1.0], "speed": [20.0, 90.0],
    }).astype(str)


def test_factor_emissions_lie_between_empty_and_full_by_utilization():
    factors = _csv([("lorry", "street", "co2", 100, 300)], ["vehicle", "road_type", "pollutant", "empty", "full"])
    grams = emissions_by_factors(_load_rows(), _network(), factors).set_index("link_id")["co2"]
    # 2 trips x 1 km x (100 + 0.5 x 200); no factor for motorways.
    assert grams.to_dict() == {"ab": 400.0, "ad": 0.0}


def test_copert_emissions_follow_the_speed_function_and_clamp_speed():
    coefficients = _csv(
        [("rigid", "nox", grade, load, 0, 0, 10, 0, 0, 0, 1, 0, 5, 50) for grade in (-6, -4, -2, 0, 2, 4, 6) for load in (0, 50, 100)],
        ["vehicle_type", "pollutant", "gradient_bin", "payload_bin", "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "rf",
         "min_speed", "max_speed"],
    )
    coefficients.loc[coefficients["payload_bin"] == "100", "gamma"] = "20"
    vehicles = _csv([("lorry", "rigid")], ["vehicle", "vehicle_type"])
    flat = _csv([("rigid", "pm", 0.5)], ["vehicle_type", "pollutant", "emission_factor"])
    grams = emissions_by_copert(_load_rows(), _network(), vehicles, coefficients, flat).set_index("link_id")
    assert grams.loc["ab", "nox"] == pytest.approx(2 * 1.0 * 10)
    assert grams.loc["ad", "nox"] == pytest.approx(1 * 1.5 * 20)
    assert grams.loc["ab", "pm_non_exhaust"] == pytest.approx(2 * 1.0 * 0.5)


def test_copert_speed_function():
    coefficients = {"alpha": 1, "beta": 0, "gamma": 0, "delta": 0, "epsilon": 0, "zeta": 0, "eta": 1, "rf": 0.5}
    assert _hot_emission_factor(coefficients, [10.0]).tolist() == [50.0]
