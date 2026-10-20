import os

import geopandas
import h5py
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, box

from netsy.cli.main import main
from netsy.helpers.skims import read_skims, write_skims
from tests.fixtures import CRS


@pytest.fixture(autouse=True)
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _csv(name, rows, columns):
    pd.DataFrame(rows, columns=columns).to_csv(name, index=False)


def _write_inputs(delivery=True):
    geopandas.GeoDataFrame(
        {"zone_id": [1, 2], "region": ["in", "in"]}, geometry=[box(0, 0, 1, 1), box(2, 0, 3, 1)], crs=CRS,
    ).to_file("zones.gpkg")
    geopandas.GeoDataFrame(
        {"agent_id": [1, 2], "zone_id": [1, 2], "sector": ["farm", "shop"], "size": [4, 6]},
        geometry=[Point(0.5, 0.5), Point(2.5, 0.5)], crs=CRS,
    ).to_file("agents.gpkg")
    write_skims("skims.omx", [1, 2], np.array([[0, 1], [1, 0]]), np.array([[0, 2], [2, 0]]))
    _csv("production_rates.csv", [("farm", "grain", 1.0)], ["sector", "resource", "rate"])
    _csv("consumption_rates.csv", [("shop", "grain", 1.0)], ["sector", "resource", "rate"])
    _csv("shipment_totals.csv", [("in", "in", "direct", "grain", 5.0)], ["origin_region", "destination_region", "flow_type", "resource", "quantity"])
    _csv("flow_types.csv", [("direct", "agent", "agent", "origin")], ["flow_type", "origin", "destination", "decay"])
    _csv("distance_decay.csv", [(-1.0, 1.0, 1.0, 1.0)], ["alpha", "beta", "cost_per_hour", "cost_per_km"])
    _csv("shipment_sizes.csv", [("small", 2.0)], ["size_class", "quantity"])
    _csv("shipment_vehicles.csv", [("van", 2.0, 1.0, 1.0)], ["vehicle", "capacity", "cost_per_hour", "cost_per_km"])
    _csv("vehicle_choice.csv", [("van", "constant", 0.0)], ["vehicle", "term", "value"])
    if delivery:
        _csv("delivery_windows.csv", [("day", 8, 18)], ["window", "start", "end"])
        _csv("delivery_choice.csv", [("day", "constant", 0.0)], ["window", "term", "value"])


def test_writes_seeded_shipments():
    _write_inputs()
    assert main(["synth", "shipments", "--seed", "1"]) == 0
    first = geopandas.read_file("shipments.gpkg")
    assert first["quantity"].tolist() == [2.0, 2.0, 1.0]
    assert set(first["origin_agent_id"]) == {1} and set(first["window"]) == {"day"}
    assert main(["synth", "shipments", "--seed", "1", "--force"]) == 0
    assert geopandas.read_file("shipments.gpkg").equals(first)


def test_facilities_and_delivery_windows_are_optional():
    _write_inputs(delivery=False)
    assert main(["synth", "shipments"]) == 0
    assert "window" not in geopandas.read_file("shipments.gpkg").columns


def test_missing_skims_names_the_file(capsys):
    _write_inputs()
    os.remove("skims.omx")
    assert main(["synth", "shipments"]) == 1
    assert "skims.omx: not found" in capsys.readouterr().err


def test_invalid_input_writes_nothing(capsys):
    _write_inputs()
    _csv("shipment_sizes.csv", [("small", 0.0)], ["size_class", "quantity"])
    assert main(["synth", "shipments"]) == 1
    assert "shipment_sizes.csv: 'quantity' must hold numbers above 0" in capsys.readouterr().err
    assert not os.path.exists("shipments.gpkg")


def test_skims_round_trip_with_their_zone_ids():
    write_skims("skims.omx", ["a", "b"], np.eye(2), np.ones((2, 2)))
    zone_ids, time, distance = read_skims("skims.omx")
    assert zone_ids == ["a", "b"] and time.tolist() == [[1, 0], [0, 1]] and distance.sum() == 4


def test_skims_must_be_square_per_zone():
    write_skims("skims.omx", [1, 2], np.eye(2), np.ones((2, 2)))
    with h5py.File("skims.omx", "a") as file:
        del file["lookup/zone_id"]
        file["lookup/zone_id"] = np.array([1, 2, 3])
    with pytest.raises(ValueError, match="'time' must be a 3 x 3 matrix"):
        read_skims("skims.omx")
