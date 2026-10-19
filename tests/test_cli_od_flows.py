import os

import pandas as pd
import pytest

from netsy.cli.main import main


@pytest.fixture(autouse=True)
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _write_inputs():
    pd.DataFrame(
        {"resource": ["goods", "goods"], "location_id": ["origin_a", "origin_b"], "quantity": [6, 4]},
    ).to_csv("productions.csv", index=False)
    pd.DataFrame(
        {"resource": ["goods", "goods"], "location_id": ["destination_a", "destination_b"], "quantity": [3, 7]},
    ).to_csv("attractions.csv", index=False)
    pd.DataFrame(
        {
            "resource": ["goods"] * 4,
            "origin_location_id": ["origin_a", "origin_a", "origin_b", "origin_b"],
            "destination_location_id": ["destination_a", "destination_b"] * 2,
            "weight": [4, 1, 1, 4],
        },
    ).to_csv("od_prior.csv", index=False)


def test_writes_balanced_od_flows():
    _write_inputs()
    assert main(["synth", "od-flows"]) == 0
    flows = pd.read_csv("od_flows.csv")
    assert flows.groupby("origin_location_id")["quantity"].sum().to_dict() == pytest.approx(
        {"origin_a": 6, "origin_b": 4},
    )


def test_refuses_to_overwrite_without_force(capsys):
    _write_inputs()
    open("od_flows.csv", "w").write("keep me")
    assert main(["synth", "od-flows"]) == 1
    assert "--force" in capsys.readouterr().err
    assert open("od_flows.csv").read() == "keep me"
