import os

import geopandas
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from netsy.cli.main import main
from tests.agent_fixtures import CRS


@pytest.fixture(autouse=True)
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _write_inputs():
    geopandas.GeoDataFrame(
        {
            "transaction_id": [1],
            "resource": ["packages"],
            "quantity": [2],
            "origin_agent_id": ["origin"],
            "destination_agent_id": ["destination"],
        },
        geometry=[LineString([(0, 0), (2, 0)])],
        crs=CRS,
    ).to_file("desire_lines.gpkg", driver="GPKG")
    geopandas.GeoDataFrame(
        {"facility_id": ["hub"], "facility_type": ["microhub"], "capacity": [2]},
        geometry=[Point(1, 0)],
        crs=CRS,
    ).to_file("facilities.gpkg", driver="GPKG")
    pd.DataFrame({"transaction_id": [1], "sequence": [1], "facility_id": ["hub"]}).to_csv(
        "facility_chain_steps.csv", index=False,
    )


def test_writes_transaction_legs():
    _write_inputs()
    assert main(["synth", "facility-chains"]) == 0
    legs = geopandas.read_file("transaction_legs.gpkg")
    assert legs["destination_agent_id"].tolist() == ["facility:hub", "destination"]


def test_refuses_to_overwrite_without_force(capsys):
    _write_inputs()
    open("transaction_legs.gpkg", "w").write("keep me")
    assert main(["synth", "facility-chains"]) == 1
    assert "--force" in capsys.readouterr().err
    assert open("transaction_legs.gpkg").read() == "keep me"
