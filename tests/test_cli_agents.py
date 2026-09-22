import os

import geopandas
import pandas as pd
import pytest

from netsy.cli.main import main
from tests.appendix import EFFECT_ROWS, THRESHOLD_ROWS
from tests.agent_fixtures import CRS, zones


@pytest.fixture(autouse=True)
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _write_inputs():
    """Run the four combiners on the appendix example, so agents is fed the
    same files the earlier commands produce."""
    for prefix in ("supply", "demand", "capacity", "need"):
        pd.DataFrame(EFFECT_ROWS, columns=["stratum", "stratum_value", "resource_1", "resource_2"]).to_csv(f"{prefix}_effects.csv", index=False)
        pd.DataFrame(THRESHOLD_ROWS, columns=["resource", "resource_level", "threshold"]).to_csv(f"{prefix}_thresholds.csv", index=False)
    for command in ("supply", "demand", "capacities", "needs"):
        assert main(["synth", command]) == 0
    zones().to_file("zones.gpkg", driver="GPKG")


def test_end_to_end_from_the_combiner_outputs():
    _write_inputs()
    assert main(["synth", "agents", "--seed", "1"]) == 0
    table = geopandas.read_file("agents.gpkg")
    assert table.crs == CRS
    assert table["agent_id"].tolist() == list(range(1, len(table) + 1))
    assert list(table.columns[:4]) == ["agent_id", "zone_id", "stratum_1", "stratum_2"]
    assert {"resource_1_capacity", "resource_2_need", "geometry"} <= set(table.columns)
    polygons = zones().set_index("zone_id").geometry
    assert all(polygons[zone].contains(point) for zone, point in zip(table["zone_id"], table.geometry))


def test_respects_the_supply_of_every_stratum():
    _write_inputs()
    main(["synth", "agents", "--seed", "2"])
    agents = geopandas.read_file("agents.gpkg")
    supply = pd.read_csv("supply.csv", dtype={"zone_id": int})
    for row in supply.itertuples(index=False):
        mine = agents[(agents["zone_id"] == row.zone_id) & (agents["stratum_1"] == row.stratum_1) & (agents["stratum_2"] == row.stratum_2)]
        assert mine["resource_2_capacity"].sum() <= row.resource_2


def test_the_seed_makes_a_run_repeatable():
    _write_inputs()
    main(["synth", "agents", "--seed", "5"])
    first = geopandas.read_file("agents.gpkg")
    main(["synth", "agents", "--seed", "5", "--force"])
    second = geopandas.read_file("agents.gpkg")
    assert first.equals(second)
    main(["synth", "agents", "--seed", "6", "--force"])
    assert not first.equals(geopandas.read_file("agents.gpkg"))


def test_refuses_to_overwrite_without_force(capsys):
    _write_inputs()
    open("agents.gpkg", "w").write("keep me")
    assert main(["synth", "agents"]) == 1
    assert "--force" in capsys.readouterr().err
    assert open("agents.gpkg").read() == "keep me"


def test_missing_input_names_the_file(capsys):
    _write_inputs()
    os.remove("zones.gpkg")
    assert main(["synth", "agents"]) == 1
    assert "zones.gpkg: not found" in capsys.readouterr().err


def test_invalid_input_names_the_file_and_writes_nothing(capsys):
    _write_inputs()
    pd.read_csv("capacities.csv").assign(probability=2.0).to_csv("capacities.csv", index=False)
    assert main(["synth", "agents"]) == 1
    assert "capacities.csv:" in capsys.readouterr().err
    assert not os.path.exists("agents.gpkg")


def test_skipped_strata_are_reported_but_not_fatal(capsys):
    _write_inputs()
    geopandas.GeoDataFrame({"zone_id": [1]}, geometry=zones().geometry[:1], crs=CRS).to_file("zones.gpkg", driver="GPKG")
    assert main(["synth", "agents", "--seed", "1"]) == 0
    assert "warning:" in capsys.readouterr().err
    assert set(geopandas.read_file("agents.gpkg")["zone_id"]) == {1}


def test_seed_is_only_an_agents_option():
    with pytest.raises(SystemExit):
        main(["synth", "supply", "--seed", "1"])
