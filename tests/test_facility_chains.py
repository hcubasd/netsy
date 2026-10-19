import geopandas
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from netsy.synth.facility_chains import facility_chains
from tests.fixtures import CRS


def _transactions():
    return geopandas.GeoDataFrame(
        {
            "transaction_id": ["shipment-1"],
            "resource": ["packages"],
            "quantity": [4],
            "origin_agent_id": ["supplier"],
            "destination_agent_id": ["household"],
        },
        geometry=[LineString([(0, 0), (4, 0)])],
        crs=CRS,
    )


def _facilities(capacity=4):
    return geopandas.GeoDataFrame(
        {"facility_id": ["ucc"], "facility_type": ["consolidation_center"], "capacity": [capacity]},
        geometry=[Point(2, 0)],
        crs=CRS,
    )


def test_facility_chain_turns_one_transaction_into_ordered_legs():
    legs = facility_chains(
        _transactions(),
        _facilities(),
        pd.DataFrame({"transaction_id": ["shipment-1"], "sequence": [1], "facility_id": ["ucc"]}),
    )
    assert legs[["leg_id", "origin_agent_id", "destination_agent_id"]].to_dict("records") == [
        {"leg_id": "shipment-1:1", "origin_agent_id": "supplier", "destination_agent_id": "facility:ucc"},
        {"leg_id": "shipment-1:2", "origin_agent_id": "facility:ucc", "destination_agent_id": "household"},
    ]
    assert legs["quantity"].tolist() == [4, 4]
    assert list(legs.geometry.iloc[0].coords) == [(0, 0), (2, 0)]
    assert list(legs.geometry.iloc[1].coords) == [(2, 0), (4, 0)]


def test_direct_transaction_remains_a_single_leg_without_a_chain_step():
    legs = facility_chains(_transactions(), _facilities(), pd.DataFrame(columns=["transaction_id", "sequence", "facility_id"]))
    assert len(legs) == 1
    assert legs["leg_id"].tolist() == ["shipment-1:1"]


def test_facility_capacity_is_an_explicit_constraint():
    with pytest.raises(ValueError, match="capacity is insufficient"):
        facility_chains(
            _transactions(),
            _facilities(capacity=3),
            pd.DataFrame({"transaction_id": ["shipment-1"], "sequence": [1], "facility_id": ["ucc"]}),
        )
