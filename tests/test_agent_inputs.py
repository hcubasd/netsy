import numpy as np
import pandas as pd
import pytest

from netsy.helpers.agent_inputs import combine_agent_inputs
from tests.agent_fixtures import aggregate, distribution, zones

COLUMNS = ["zone_id", "sector", "grain", "parcels"]


def _inputs():
    supply = aggregate([("1", "a", "4", None), ("2", "a", "6", "3")], COLUMNS)
    demand = aggregate([("1", "a", "4", None), ("2", "a", "6", "3")], COLUMNS)
    capacities = distribution([
        (1, "a", "grain", 0, 0.5), (1, "a", "grain", 2, 0.5),
        (2, "a", "grain", 2, 1.0), (2, "a", "parcels", 1, 1.0),
    ])
    needs = distribution([
        (1, "a", "grain", 2, 1.0), (2, "a", "grain", 2, 1.0), (2, "a", "parcels", 1, 1.0),
    ])
    return supply, demand, capacities, needs, zones()


def test_matches_strata_and_usable_resources():
    inputs = combine_agent_inputs(*_inputs())
    assert inputs.dims == ["zone_id", "sector"]
    assert inputs.resources == ["grain", "parcels"]
    assert [list(s.resources) for s in inputs.strata] == [["grain"], ["grain", "parcels"]]


def test_zone_id_keeps_the_type_it_has_in_the_zones_file():
    inputs = combine_agent_inputs(*_inputs())
    assert [s.dims["zone_id"] for s in inputs.strata] == [1, 2]
    assert all(isinstance(s.dims["zone_id"], (int, np.integer)) for s in inputs.strata)
    assert [s.dims["sector"] for s in inputs.strata] == ["a", "a"]


def test_a_stratum_is_paired_with_the_polygon_of_its_zone():
    inputs = combine_agent_inputs(*_inputs())
    assert [s.polygon.bounds for s in inputs.strata] == [(0, 0, 1, 1), (2, 0, 3, 1)]


def test_resource_levels_and_cumulative_probabilities_are_ready_to_draw_from():
    resource = combine_agent_inputs(*_inputs()).strata[0].resources["grain"]
    assert (resource.supply, resource.demand) == (4, 4)
    assert resource.capacity_levels.tolist() == [0, 2]
    assert resource.capacity_cumulative.tolist() == [0.5, 1.0]


def test_a_resource_missing_from_needs_is_left_out():
    supply, demand, capacities, needs, z = _inputs()
    needs = needs[needs["resource"] != "parcels"]
    inputs = combine_agent_inputs(supply, demand, capacities, needs, z)
    assert [list(s.resources) for s in inputs.strata] == [["grain"], ["grain"]]


def test_a_resource_without_demand_is_left_out():
    supply, demand, capacities, needs, z = _inputs()
    demand.loc[1, "parcels"] = None
    inputs = combine_agent_inputs(supply, demand, capacities, needs, z)
    assert list(inputs.strata[1].resources) == ["grain"]


def test_strata_that_yield_nothing_are_reported():
    supply, demand, capacities, needs, z = _inputs()
    supply.loc[len(supply)] = ["9", "a", "3", None]
    demand.loc[len(demand)] = ["9", "a", "3", None]
    with pytest.warns(UserWarning, match=r"1 of 3 strata yield no agents"):
        inputs = combine_agent_inputs(supply, demand, capacities, needs, z)
    assert len(inputs.strata) == 2


def test_a_stratum_missing_from_demand_yields_nothing():
    supply, demand, capacities, needs, z = _inputs()
    with pytest.warns(UserWarning, match="yield no agents"):
        inputs = combine_agent_inputs(supply, demand.iloc[[1]], capacities, needs, z)
    assert len(inputs.strata) == 1


def test_no_warning_when_every_stratum_is_used(recwarn):
    combine_agent_inputs(*_inputs())
    assert not [w for w in recwarn if "yield no agents" in str(w.message)]


def test_capacities_and_needs_must_share_their_strata_columns():
    supply, demand, capacities, needs, z = _inputs()
    with pytest.raises(ValueError, match="same stratum columns"):
        combine_agent_inputs(supply, demand, capacities, needs.drop(columns="sector"), z)


def test_zone_id_is_required():
    supply, demand, capacities, needs, z = _inputs()
    with pytest.raises(ValueError, match="zone_id"):
        combine_agent_inputs(supply, demand, capacities.drop(columns="zone_id"), needs.drop(columns="zone_id"), z)


def test_supply_must_have_the_stratum_columns():
    supply, demand, capacities, needs, z = _inputs()
    with pytest.raises(ValueError, match="supply: missing stratum columns"):
        combine_agent_inputs(supply.drop(columns="sector"), demand, capacities, needs, z)


def test_a_stratum_column_missing_from_capacities_is_reported_not_swallowed():
    supply, demand, capacities, needs, z = _inputs()
    supply["region"] = ["north", "south"]
    with pytest.raises(ValueError, match="'region' is not numeric"):
        combine_agent_inputs(supply, demand, capacities, needs, z)


@pytest.mark.parametrize("value", ["-1", "2.5"])
def test_amounts_must_be_whole_and_not_negative(value):
    supply, demand, capacities, needs, z = _inputs()
    supply.loc[0, "grain"] = value
    with pytest.raises(ValueError, match="whole numbers"):
        combine_agent_inputs(supply, demand, capacities, needs, z)


def test_a_whole_number_written_with_a_decimal_point_is_accepted():
    supply, demand, capacities, needs, z = _inputs()
    supply.loc[0, "grain"] = "4.0"
    assert combine_agent_inputs(supply, demand, capacities, needs, z).strata[0].resources["grain"].supply == 4


def test_a_stratum_may_appear_only_once():
    supply, demand, capacities, needs, z = _inputs()
    with pytest.raises(ValueError, match="only once"):
        combine_agent_inputs(pd.concat([supply, supply.head(1)]), demand, capacities, needs, z)
