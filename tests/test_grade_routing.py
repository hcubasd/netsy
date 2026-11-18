"""Grade penalties change paths without changing trip quantities or defaults."""

import numpy as np
import pandas as pd
import pytest

from netsy.synth.network_loads import network_loads
from tests.test_network import _csv, _network, _speeds, _trips, _zones

UP = "uphill_cost_per_km_per_percent"
DOWN = "downhill_cost_per_km_per_percent"


def _assign(vehicles, network=None, trips=None, road_costs=None, **options):
    # Equal endpoint elevations: the short street climbs and descends a hill;
    # the longer bypass is flat. Grades follow from_node -> to_node.
    if network is None:
        network = _network()
        network["grade"] = network.link_id.map({"ab": 5, "bc": -5, "ba": -5, "cb": 5}).fillna(0)
    if trips is None:
        trips = _trips([(7, "slope", .5, 1, 3, "goods")])
    if road_costs is None:
        road_costs = _csv([], ["road_type", "speed_class", "cost"])
    return network_loads(network, _zones(), vehicles, _speeds(), road_costs,
                         _csv([("day", 0, 24)], ["time_interval", "start", "end"]),
                         {"trips": trips}, None, None, **options)


def _vehicles(up=0, down=0):
    return _csv([("slope", "truck", 0, 1, up, down)],
                ["vehicle", "speed_class", "cost_per_hour", "cost_per_km", UP, DOWN])


def test_grade_changes_path_and_does_not_merge_vehicle_routing_preferences():
    vehicles = pd.concat([_vehicles(up=1), _vehicles().assign(vehicle="plain")], ignore_index=True)
    trips = _trips([(7, "slope", .5, 1, 3, "goods"), (7, "plain", .5, 1, 3, "goods")])
    loads = _assign(vehicles, trips=trips)
    assert set(loads[loads.vehicle == "slope"].link_id) == {"ad", "dc"}
    assert set(loads[loads.vehicle == "plain"].link_id) == {"ab", "bc"}
    assert (loads.trips == 1).all() and (loads.utilization == .5).all()


@pytest.mark.parametrize("up,down", [(1, 0), (0, 1)])
def test_signed_uphill_and_downhill_penalties_both_avoid_hilly_path(up, down):
    assert set(_assign(_vehicles(up, down)).link_id) == {"ad", "dc"}


def test_penalty_uses_percentage_points_and_kilometres():
    # Street cost = 2 + (1 km * 5 percentage points * coefficient).
    # Bypass cost = 3. The threshold is therefore 0.2, not 20 or 0.002.
    assert set(_assign(_vehicles(up=.19)).link_id) == {"ab", "bc"}
    assert set(_assign(_vehicles(up=.21)).link_id) == {"ad", "dc"}


def test_reverse_arcs_use_signed_grade_not_geometry_direction():
    # Restrict to one directed link at a time to isolate the sign handling.
    for link, grade, origin, destination in [("ab", 5, 1, 2), ("ba", -5, 2, 1)]:
        # Compare each arc against a longer flat parallel-in-purpose path.
        network = pd.DataFrame({
            "link_id": [link, "detour1", "detour2"],
            "from_node": [origin, origin, 4], "to_node": [destination, 4, destination],
            "length": [1, 1, 1], "road_type": "street", "grade": [grade, 0, 0],
        })
        zones = pd.DataFrame({"zone_id": [origin, destination], "node": [origin, destination]})
        speeds = pd.DataFrame({"link_id": network.link_id, "speed_class": "truck", "speed": 30})
        loads = network_loads(network, zones, _vehicles(up=1), speeds,
                              _csv([], ["road_type", "speed_class", "cost"]),
                              _csv([("day", 0, 24)], ["time_interval", "start", "end"]),
                              {"trip": _trips([(7, "slope", 0, origin, destination, "goods")])}, None, None)
        assert set(loads.link_id) == ({"detour1", "detour2"} if grade > 0 else {link})


def test_absent_blank_and_zero_coefficients_keep_legacy_paths():
    plain = _assign(_vehicles().drop(columns=[UP, DOWN]), network=_network())
    for vehicles in [_vehicles(), _vehicles(up=None, down="")]:
        pd.testing.assert_frame_equal(plain, _assign(vehicles))


def test_flat_grades_keep_baseline_even_when_penalties_are_enabled():
    baseline = _assign(_vehicles().drop(columns=[UP, DOWN]), network=_network())
    graded = _assign(_vehicles(up=1, down=2), network=_network().assign(grade=0))
    pd.testing.assert_frame_equal(baseline, graded)


@pytest.mark.parametrize("value", [-1, np.inf, "invalid"])
@pytest.mark.parametrize("column", [UP, DOWN])
def test_invalid_coefficients_fail(value, column):
    vehicles = _vehicles()
    vehicles[column] = str(value)
    with pytest.raises(ValueError, match="finite nonnegative"):
        _assign(vehicles)


@pytest.mark.parametrize("grade", [None, np.nan, np.inf, "invalid"])
def test_enabled_routing_requires_complete_finite_grades(grade):
    network = _network()
    if grade is not None:
        network["grade"] = grade
    with pytest.raises(ValueError, match="grade"):
        _assign(_vehicles(up=1), network=network)


def test_worker_count_does_not_change_grade_aware_loads():
    pd.testing.assert_frame_equal(_assign(_vehicles(up=1)), _assign(_vehicles(up=1), workers=2))


@pytest.mark.parametrize("operation,cost", [("exclude", 0), ("replace", .1)])
def test_road_rules_keep_priority_over_grade_penalties(operation, cost):
    road = "motorway" if operation == "exclude" else "street"
    rules = _csv([(road, "truck", cost, operation)], ["road_type", "speed_class", "cost", "operation"])
    assert set(_assign(_vehicles(up=1), road_costs=rules).link_id) == {"ab", "bc"}


def test_negative_final_weights_fail_instead_of_running_dijkstra():
    rules = _csv([("street", "truck", -1)], ["road_type", "speed_class", "cost"])
    with pytest.raises(ValueError, match="nonnegative.*Dijkstra"):
        _assign(_vehicles(up=1), road_costs=rules)


def test_matrix_trips_also_use_grade_costs():
    network = _network().assign(grade=[5, -5, 0, 0, -5, 5, 0, 0])
    matrix = np.zeros((3, 3)); matrix[0, 1] = 2.5
    assignment = _csv([("service", "slope", "service", .4, 0)],
                      ["matrix", "vehicle", "segment", "utilization", "minimum"])
    loads = network_loads(network, _zones(), _vehicles(up=1), _speeds(),
                          _csv([], ["road_type", "speed_class", "cost"]),
                          _csv([("day", 0, 24)], ["time_interval", "start", "end"]),
                          {}, (["1", "3", "9"], {"service": matrix}), assignment)
    assert set(loads.link_id) == {"ad", "dc"}
    assert loads.trips.tolist() == [2.5, 2.5]
    assert loads.utilization.tolist() == [.4, .4]
