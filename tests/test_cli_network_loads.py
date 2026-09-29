import os

import geopandas
import pandas as pd
import pytest
from shapely.geometry import LineString

from netsy.cli.main import main
from tests.agent_fixtures import CRS


@pytest.fixture(autouse=True)
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _write_inputs():
    geopandas.GeoDataFrame(
        {"link_id": [0, 1], "grade": [0.0, 0.0], "road_type": ["road", "road"], "oneway": [False, False]},
        geometry=[LineString([(0, 0), (1, 0)]), LineString([(1, 0), (2, 0)])],
        crs=CRS,
    ).to_file("network.gpkg", driver="GPKG")
    geopandas.GeoDataFrame(
        {"resource": ["parcels", "parcels"], "quantity": [2, 2], "origin_agent_id": [1, 1]},
        geometry=[LineString([(0, 0), (1, 0)]), LineString([(0, 0), (2, 0)])],
        crs=CRS,
    ).to_file("desire_lines.gpkg", driver="GPKG")
    pd.DataFrame([["parcels", "day", 1.0]], columns=["resource", "time_interval", "probability"]).to_csv("departures.csv", index=False)
    pd.DataFrame([["day", 100.0]], columns=["time_interval", "duration"]).to_csv("time_intervals.csv", index=False)
    pd.DataFrame([["parcels", 0.0]], columns=["resource", "dwell_time"]).to_csv("dwell_times.csv", index=False)
    pd.DataFrame([["van", 0.15, 4.0, -1.0, -1.0, 1.0]], columns=[
        "vehicle", "bpr_alpha", "bpr_beta", "time_coefficient", "distance_coefficient", "pcu",
    ]).to_csv("vehicles.csv", index=False)
    pd.DataFrame([["van", "road", 1.0]], columns=["vehicle", "road_type", "velocity"]).to_csv("vehicle_velocities.csv", index=False)
    pd.DataFrame([["van", "parcels", 4]], columns=["vehicle", "resource", "capacity"]).to_csv("vehicle_capacities.csv", index=False)
    pd.DataFrame([["road", 100.0]], columns=["road_type", "capacity"]).to_csv("road_capacities.csv", index=False)
    pd.DataFrame([["van", "parcels", 0.0]], columns=[
        "vehicle", "resource", "alternative_specific_constant",
    ]).to_csv("alternative_specific_constants.csv", index=False)


def test_writes_seeded_network_loads():
    _write_inputs()
    assert main(["synth", "network-loads", "--seed", "1"]) == 0
    first = pd.read_csv("network_loads.csv")
    assert set(first.columns) == {
        "link_id", "time_interval", "resource", "vehicle", "forward", "vehicle_count", "velocity", "load_pct",
    }
    assert main(["synth", "network-loads", "--seed", "1", "--force"]) == 0
    assert first.equals(pd.read_csv("network_loads.csv"))


def test_requires_all_inputs(capsys):
    assert main(["synth", "network-loads"]) == 1
    assert "network.gpkg: not found" in capsys.readouterr().err


def test_dwell_times_rejects_removed_return_load(capsys):
    _write_inputs()
    os.remove("dwell_times.csv")
    pd.DataFrame([["parcels", 0.0, 0.5]], columns=["resource", "dwell_time", "load_pct"]).to_csv("dwell_times.csv", index=False)
    assert main(["synth", "network-loads"]) == 1
    assert "'load_pct' was removed" in capsys.readouterr().err
