import numpy as np
import pytest
from shapely.geometry import LineString

from netsy.synth.network_loads import _targets, network_loads


def _inputs(capacity=4, oneway=False):
    network = [
        {"link_id": 0, "grade": 0.0, "road_type": "road", "oneway": oneway, "geometry": LineString([(0, 0), (1, 0)])},
        {"link_id": 1, "grade": 0.0, "road_type": "road", "oneway": oneway, "geometry": LineString([(1, 0), (2, 0)])},
    ]
    desire_lines = [
        {"resource": "parcels", "quantity": 2, "origin_agent_id": 1, "geometry": LineString([(0, 0), (1, 0)])},
        {"resource": "parcels", "quantity": 2, "origin_agent_id": 1, "geometry": LineString([(0, 0), (2, 0)])},
    ]
    departures = [{"resource": "parcels", "time_interval": "day", "probability": 1.0}]
    intervals = [{"time_interval": "day", "duration": 100.0}]
    dwell = [{"resource": "parcels", "dwell_time": 0.0}]
    vehicles = [{
        "vehicle": "van", "bpr_alpha": 0.15, "bpr_beta": 4.0,
        "time_coefficient": -1.0, "distance_coefficient": -1.0, "pcu": 1.0,
    }]
    velocities = [{"vehicle": "van", "road_type": "road", "velocity": 1.0}]
    capacities = [{"vehicle": "van", "resource": "parcels", "capacity": capacity}]
    road_capacities = [{"road_type": "road", "capacity": 100.0}]
    asc = [{"vehicle": "van", "resource": "parcels", "alternative_specific_constant": 0.0}]
    return network, desire_lines, departures, intervals, dwell, vehicles, velocities, capacities, road_capacities, asc


def _synth(*args, seed=1):
    return network_loads(*args, rng=np.random.default_rng(seed))


def test_interval_targets_preserve_the_resource_total():
    lines = [{"resource": "parcels", "quantity": 3}]
    departures = [
        {"resource": "parcels", "time_interval": "a", "probability": 0.5},
        {"resource": "parcels", "time_interval": "b", "probability": 0.5},
    ]
    targets = _targets(lines, departures, ["a", "b"])
    assert targets == {("parcels", "a"): 2, ("parcels", "b"): 1}


def test_capacity_tour_visits_both_recipients_and_returns_empty():
    rows = _synth(*_inputs())
    assert {(row["link_id"], row["forward"]) for row in rows} == {(0, True), (1, True), (0, False), (1, False)}
    by_traversal = {(row["link_id"], row["forward"]): row["load_pct"] for row in rows}
    assert by_traversal[(0, True)] == 1.0
    assert by_traversal[(1, True)] == 0.5
    assert by_traversal[(0, False)] == 0.0
    assert by_traversal[(1, False)] == 0.0


def test_capacity_limit_creates_additional_tours():
    rows = _synth(*_inputs(capacity=3))
    outbound = [row for row in rows if row["link_id"] == 0 and row["forward"]]
    assert sum(row["vehicle_count"] for row in outbound) == 2


def test_seed_makes_the_loads_repeatable():
    first = _synth(*_inputs(), seed=2)
    assert first == _synth(*_inputs(), seed=2)


def test_unreturnable_oneway_delivery_is_warned_and_not_loaded():
    with pytest.warns(UserWarning, match="unable to route"):
        assert _synth(*_inputs(oneway=True)) == []
