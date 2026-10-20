import os

import geopandas
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, box

from netsy.cli.main import main
from netsy.helpers.skims import write_skims
from tests.fixtures import CRS


@pytest.fixture(autouse=True)
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _write_inputs():
    geopandas.GeoDataFrame(
        {"zone_id": [1, 2], "region": ["in", "in"]}, geometry=[box(0, 0, 1, 1), box(2, 0, 3, 1)], crs=CRS,
    ).to_file("zones.gpkg")
    write_skims("skims.omx", [1, 2], np.array([[0, 1], [1, 0]]), np.array([[0, 10], [10, 0]]))
    geopandas.GeoDataFrame(
        {"transaction_id": [1, 2], "resource": ["grain", "grain"], "quantity": [1.0, 6.0], "vehicle": ["van", "van"],
         "origin_zone_id": [1, 1], "destination_zone_id": [2, 2]},
        geometry=[LineString([(0.5, 0.5), (2.5, 0.5)])] * 2, crs=CRS,
    ).to_file("shipments.gpkg")
    pd.DataFrame([("van", 4.0, 1, 1)], columns=["vehicle", "capacity", "cost_per_hour", "cost_per_km"]).to_csv("shipment_vehicles.csv", index=False)
    pd.DataFrame([("independent_carriers", 1)], columns=["setting", "value"]).to_csv("tour_settings.csv", index=False)
    for name in ("end_tour_first.csv", "end_tour_later.csv"):
        pd.DataFrame([("constant", 50)], columns=["term", "value"]).to_csv(name, index=False)


def test_writes_tours_and_their_shipments():
    _write_inputs()
    assert main(["synth", "tours", "--seed", "1"]) == 0
    trips = geopandas.read_file("tours.gpkg")
    parts = pd.read_csv("tour_shipments.csv")
    assert trips["tour_id"].nunique() == 3
    assert parts.groupby("transaction_id")["quantity"].sum().tolist() == [1.0, 6.0]


def test_refuses_to_overwrite_either_output_without_force(capsys):
    _write_inputs()
    with open("tour_shipments.csv", "w") as f:
        f.write("keep me")
    assert main(["synth", "tours"]) == 1
    assert "tour_shipments.csv: already exists" in capsys.readouterr().err
    assert not os.path.exists("tours.gpkg")


def test_missing_input_names_the_file(capsys):
    _write_inputs()
    os.remove("end_tour_later.csv")
    assert main(["synth", "tours"]) == 1
    assert "end_tour_later.csv: not found" in capsys.readouterr().err
