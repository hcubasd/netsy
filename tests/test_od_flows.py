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


def test_ipf_balances_marginals_without_creating_unsupported_pairs():
    flows = od_flows(*_marginals())
    assert flows.groupby("origin_location_id")["quantity"].sum().to_dict() == pytest.approx(
        {"origin_a": 6, "origin_b": 4},
    )
    assert flows.groupby("destination_location_id")["quantity"].sum().to_dict() == pytest.approx(
        {"destination_a": 3, "destination_b": 7},
    )
    assert set(flows.columns) == {"resource", "origin_location_id", "destination_location_id", "quantity"}


def test_unbalanced_marginals_fail_explicitly():
    productions, attractions, prior = _marginals()
    attractions.loc[0, "quantity"] = 2
    with pytest.raises(ValueError, match="does not equal"):
        od_flows(productions, attractions, prior)


def test_missing_prior_support_fails_explicitly():
    productions, attractions, prior = _marginals()
    prior = prior.loc[prior["origin_location_id"] != "origin_b"]
    with pytest.raises(ValueError, match="no supported destination"):
        od_flows(productions, attractions, prior)
