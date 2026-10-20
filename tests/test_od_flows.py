import pandas as pd
import pytest

from netsy.synth.od_flows import od_flows


def _marginals():
    productions = pd.DataFrame(
        {"resource": ["goods", "goods"], "location_id": ["origin_a", "origin_b"], "quantity": [6, 4]},
    )
    attractions = pd.DataFrame(
        {"resource": ["goods", "goods"], "location_id": ["destination_a", "destination_b"], "quantity": [3, 7]},
    )
    prior = pd.DataFrame(
        {
            "resource": ["goods"] * 4,
            "origin_location_id": ["origin_a", "origin_a", "origin_b", "origin_b"],
            "destination_location_id": ["destination_a", "destination_b"] * 2,
            "weight": [4, 1, 1, 4],
        },
    )
    return productions, attractions, prior


def test_fratar_balances_marginals_without_creating_unsupported_pairs():
    flows = od_flows(*_marginals())
    assert flows.groupby("origin_location_id")["quantity"].sum().to_dict() == pytest.approx(
        {"origin_a": 6, "origin_b": 4},
    )
    # MASS-GT's tolerance leaves the attractions within about 0.1%.
    assert flows.groupby("destination_location_id")["quantity"].sum().to_dict() == pytest.approx(
        {"destination_a": 3, "destination_b": 7}, rel=1e-3,
    )
    assert set(flows.columns) == {"resource", "origin_location_id", "destination_location_id", "quantity"}


def test_unequal_totals_match_the_productions_and_come_near_the_attractions():
    productions, attractions, prior = _marginals()
    attractions.loc[0, "quantity"] = 2
    flows = od_flows(productions, attractions, prior)
    assert flows.groupby("origin_location_id")["quantity"].sum().to_dict() == pytest.approx({"origin_a": 6, "origin_b": 4})
    columns = flows.groupby("destination_location_id")["quantity"].sum()
    assert columns["destination_a"] < 3 and columns["destination_b"] > 7


def test_iterations_stop_at_the_tolerance_on_the_largest_scaling_factor():
    loose = od_flows(*_marginals(), tolerance=0.5, max_iterations=50)
    strict = od_flows(*_marginals(), tolerance=1e-9, max_iterations=500)
    assert loose.groupby("destination_location_id")["quantity"].sum()["destination_a"] != pytest.approx(3, abs=1e-6)
    # The convergence measure is rounded to five decimals, as MASS-GT's is.
    assert strict.groupby("destination_location_id")["quantity"].sum().to_dict() == pytest.approx(
        {"destination_a": 3, "destination_b": 7}, abs=1e-4,
    )


def test_a_marginal_without_prior_support_stays_unmet_with_a_warning():
    productions, attractions, prior = _marginals()
    prior = prior.loc[prior["origin_location_id"] != "origin_b"]
    with pytest.warns(UserWarning, match=r"no flow to the production of \['origin_b'\]"):
        flows = od_flows(productions, attractions, prior)
    assert set(flows["origin_location_id"]) == {"origin_a"}
