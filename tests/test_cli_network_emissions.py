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
    pd.DataFrame([{
        "link_id": 0, "time_interval": "day", "resource": "parcels", "vehicle": "van",
        "forward": True, "vehicle_count": 1, "velocity": 10.0, "load_pct": 1.0,
    }]).to_csv("network_loads.csv", index=False)
    geopandas.GeoDataFrame(
        {"link_id": [0], "grade": [0.0]},
        geometry=[LineString([(0, 0), (2000, 0)])],
        crs=CRS,
    ).to_file("network.gpkg", driver="GPKG")
    pd.DataFrame([["van", "light"]], columns=["vehicle", "vehicle_type"]).to_csv("vehicles.csv", index=False)
    pd.DataFrame([
        ["light", "nox", gradient, payload, 0, 0, 6, 0, 0, 0, 2, 0]
        for gradient in (-6, -4, -2, 0, 2, 4, 6)
        for payload in (0, 50, 100)
    ], columns=[
        "vehicle_type", "pollutant", "gradient_bin", "payload_bin",
        "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "rf",
    ]).to_csv("copert_v_coefficients.csv", index=False)
    pd.DataFrame([["light", "pm10", 0.5]], columns=[
        "vehicle_type", "pollutant", "emission_factor",
    ]).to_csv("emission_factors.csv", index=False)


def test_writes_copert_and_non_exhaust_emissions():
    _write_inputs()
    assert main(["synth", "network-emissions"]) == 0
    table = pd.read_csv("network_emissions.csv")
    assert set(table["source"]) == {"exhaust", "non-exhaust"}
    assert sorted(table["grams"]) == [1.0, 6.0]


def test_missing_input_names_the_file(capsys):
    assert main(["synth", "network-emissions"]) == 1
    assert "network_loads.csv: not found" in capsys.readouterr().err


def test_refuses_to_overwrite_without_force(capsys):
    _write_inputs()
    open("network_emissions.csv", "w").write("keep me")
    assert main(["synth", "network-emissions"]) == 1
    assert "--force" in capsys.readouterr().err
