import os

import geopandas
import pandas as pd
import pytest
from shapely.geometry import box

from netsy.cli.main import main
from tests.fixtures import CRS


@pytest.fixture(autouse=True)
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _write_inputs():
    geopandas.GeoDataFrame({"zone_id": [1, 2]}, geometry=[box(0, 0, 1, 1), box(2, 0, 3, 1)], crs=CRS).to_file("zones.gpkg")
    pd.DataFrame({"zone_id": [1, 2], "sector": ["shop", "shop"], "size": [10, 6]}).to_csv("size_totals.csv", index=False)
    pd.DataFrame({"sector": ["shop"], "size_min": [1], "size_max": [3], "probability": [1.0]}).to_csv("size_classes.csv", index=False)


def test_writes_seeded_agents():
    _write_inputs()
    assert main(["synth", "agents", "--seed", "1"]) == 0
    first = geopandas.read_file("agents.gpkg")
    assert list(first.columns) == ["agent_id", "zone_id", "sector", "size", "geometry"]
    assert (first["size"] >= 1).all()
    assert main(["synth", "agents", "--seed", "1", "--force"]) == 0
    assert geopandas.read_file("agents.gpkg").equals(first)


def test_min_size_drops_small_agents():
    _write_inputs()
    assert main(["synth", "agents", "--seed", "1", "--min-size", "3"]) == 0
    assert (geopandas.read_file("agents.gpkg")["size"] >= 3).all()


def test_refuses_to_overwrite_without_force(capsys):
    _write_inputs()
    with open("agents.gpkg", "w") as f:
        f.write("keep me")
    assert main(["synth", "agents"]) == 1
    assert "--force" in capsys.readouterr().err
    assert open("agents.gpkg").read() == "keep me"


def test_missing_input_names_the_file(capsys):
    _write_inputs()
    os.remove("size_classes.csv")
    assert main(["synth", "agents"]) == 1
    assert "size_classes.csv: not found" in capsys.readouterr().err


def test_invalid_input_writes_nothing(capsys):
    _write_inputs()
    pd.DataFrame({"sector": ["shop"], "size_min": [1], "size_max": [3], "probability": [0.5]}).to_csv("size_classes.csv", index=False)
    assert main(["synth", "agents"]) == 1
    assert "size_classes.csv: the probabilities of each agent class must sum to one" in capsys.readouterr().err
    assert not os.path.exists("agents.gpkg")
