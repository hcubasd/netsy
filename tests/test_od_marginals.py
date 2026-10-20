import pandas as pd
import pytest

from netsy.synth.od_marginals import od_marginals


def _inputs():
    attributes = pd.DataFrame({"location_id": ["a", "b", "abroad"], "jobs": [10, 20, None], "floor": [1, 0, None]})
    coefficients = pd.DataFrame({
        "resource": ["goods", "goods"], "attribute": ["jobs", "floor"], "production": [2, 100], "attraction": [1, 0],
    })
    prior = pd.DataFrame({
        "resource": ["goods"] * 3, "origin_location_id": ["abroad", "abroad", "a"],
        "destination_location_id": ["a", "elsewhere", "abroad"], "weight": [5, 7, 3],
    })
    return attributes, coefficients, prior


def test_marginals_are_linear_in_the_attributes():
    productions, attractions = od_marginals(*_inputs())
    assert productions.set_index("location_id")["quantity"].to_dict() == {"a": 120, "b": 40, "abroad": 12}
    assert attractions.set_index("location_id")["quantity"].to_dict() == {"a": 10, "b": 20, "abroad": 3}


def test_only_listed_locations_get_marginals():
    productions, _ = od_marginals(*_inputs())
    assert "elsewhere" not in set(productions["location_id"])


def test_partly_empty_attributes_are_an_error():
    attributes, coefficients, prior = _inputs()
    attributes.loc[0, "floor"] = None
    with pytest.raises(ValueError, match="or all be empty to keep the prior totals"):
        od_marginals(attributes, coefficients, prior)


def test_an_unknown_attribute_is_an_error():
    attributes, coefficients, prior = _inputs()
    coefficients.loc[0, "attribute"] = "rooms"
    with pytest.raises(ValueError, match=r"attributes \['rooms'\] are not columns"):
        od_marginals(attributes, coefficients, prior)
