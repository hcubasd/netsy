import pandas as pd
import pytest

from netsy.cli.main import main
from tests.appendix import EFFECT_ROWS, THRESHOLD_ROWS

# (command, effects file, thresholds file, output file)
COMMANDS = [
    ("supply", "supply_effects.csv", "supply_thresholds.csv", "supply.csv"),
    ("demand", "demand_effects.csv", "demand_thresholds.csv", "demand.csv"),
    ("capacities", "capacity_effects.csv", "capacity_thresholds.csv", "capacities.csv"),
    ("needs", "need_effects.csv", "need_thresholds.csv", "needs.csv"),
]


@pytest.fixture(autouse=True)
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _write_inputs(effects_file, thresholds_file):
    pd.DataFrame(EFFECT_ROWS, columns=["stratum", "stratum_value", "resource_1", "resource_2"]).to_csv(effects_file, index=False)
    pd.DataFrame(THRESHOLD_ROWS, columns=["resource", "resource_level", "threshold"]).to_csv(thresholds_file, index=False)


@pytest.mark.parametrize("command, effects_file, thresholds_file, output", COMMANDS)
def test_writes_the_output_file(command, effects_file, thresholds_file, output):
    _write_inputs(effects_file, thresholds_file)
    assert main(["synth", command]) == 0
    assert pd.read_csv(output).shape[0] > 0


def test_supply_csv_round_trips_the_appendix_table():
    _write_inputs("supply_effects.csv", "supply_thresholds.csv")
    main(["synth", "supply"])
    table = pd.read_csv("supply.csv")
    assert list(table.columns) == ["zone_id", "stratum_1", "stratum_2", "resource_1", "resource_2"]
    assert table["resource_2"].tolist() == [5, 7, 5, 6, 8, 9, 7, 9]


def test_capacities_csv_is_long_with_probabilities():
    _write_inputs("capacity_effects.csv", "capacity_thresholds.csv")
    main(["synth", "capacities"])
    table = pd.read_csv("capacities.csv")
    assert list(table.columns) == ["zone_id", "stratum_1", "stratum_2", "resource", "resource_level", "probability"]
    assert table["probability"].sum() == pytest.approx(16)


def test_each_command_reads_its_own_files():
    _write_inputs("supply_effects.csv", "supply_thresholds.csv")
    assert main(["synth", "demand"]) == 1


def test_missing_input_exits_nonzero_with_the_path(capsys):
    assert main(["synth", "supply"]) == 1
    assert "supply_effects.csv: not found" in capsys.readouterr().err


def test_invalid_input_exits_nonzero_with_the_reason(capsys):
    _write_inputs("supply_effects.csv", "supply_thresholds.csv")
    pd.DataFrame(THRESHOLD_ROWS, columns=["resource", "resource_level", "threshold"]).assign(threshold=0.0).to_csv("supply_thresholds.csv", index=False)
    assert main(["synth", "supply"]) == 1
    assert "supply_thresholds.csv:" in capsys.readouterr().err
    assert not pd.io.common.file_exists("supply.csv")


def test_refuses_to_overwrite_without_force(capsys):
    _write_inputs("supply_effects.csv", "supply_thresholds.csv")
    with open("supply.csv", "w") as f:
        f.write("keep me")
    assert main(["synth", "supply"]) == 1
    assert "--force" in capsys.readouterr().err
    assert open("supply.csv").read() == "keep me"


def test_force_overwrites():
    _write_inputs("supply_effects.csv", "supply_thresholds.csv")
    with open("supply.csv", "w") as f:
        f.write("stale")
    assert main(["synth", "supply", "--force"]) == 0
    assert pd.read_csv("supply.csv").shape[0] == 8


def test_unknown_command_is_a_usage_error():
    with pytest.raises(SystemExit) as exit_info:
        main(["synth", "zones"])
    assert exit_info.value.code == 2
