import os

import geopandas
import pytest
from shapely.geometry import Point

from netsy.cli.main import main
from tests.agent_fixtures import CRS


@pytest.fixture(autouse=True)
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _write_agents():
    geopandas.GeoDataFrame(
        {
            "agent_id": [1, 2, 3],
            "grain_capacity": [4, 0, 0],
            "grain_need": [0, 2, 2],
        },
        geometry=[Point(0, 0), Point(1, 0), Point(2, 0)],
        crs=CRS,
    ).to_file("agents.gpkg", driver="GPKG")


def test_writes_seeded_desire_lines():
    _write_agents()
    assert main(["synth", "desire-lines", "--seed", "5"]) == 0
    first = geopandas.read_file("desire_lines.gpkg")
    assert main(["synth", "desire-lines", "--seed", "5", "--force"]) == 0
    assert first.equals(geopandas.read_file("desire_lines.gpkg"))


def test_refuses_to_overwrite_without_force(capsys):
    _write_agents()
    open("desire_lines.gpkg", "w").write("keep me")
    assert main(["synth", "desire-lines"]) == 1
    assert "--force" in capsys.readouterr().err
    assert open("desire_lines.gpkg").read() == "keep me"


def test_missing_agents_names_the_file(capsys):
    assert main(["synth", "desire-lines"]) == 1
    assert "agents.gpkg: not found" in capsys.readouterr().err


def test_invalid_agents_write_nothing(capsys):
    geopandas.GeoDataFrame({"agent_id": [1]}, geometry=[Point(0, 0)], crs=CRS).to_file("agents.gpkg", driver="GPKG")
    assert main(["synth", "desire-lines"]) == 1
    assert "agents.gpkg:" in capsys.readouterr().err
    assert not os.path.exists("desire_lines.gpkg")
