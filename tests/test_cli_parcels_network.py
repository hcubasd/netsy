import geopandas
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, box

from netsy.cli.main import main
from netsy.helpers.skims import write_skims
from tests.fixtures import CRS


@pytest.fixture(autouse=True)
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _csv(name, rows, columns):
    pd.DataFrame(rows, columns=columns).to_csv(name, index=False)


def _write_inputs():
    geopandas.GeoDataFrame(
        {"zone_id": [1, 2, 3], "node": [1, 2, 3]}, geometry=[box(i, 0, i + 1, 1) for i in range(3)], crs=CRS,
    ).to_file("zones.gpkg")
    steps = np.abs(np.subtract.outer(np.arange(3), np.arange(3)))
    write_skims("skims.omx", [1, 2, 3], steps / 60, steps)
    geopandas.GeoDataFrame(
        {"facility_id": ["hub"], "facility_type": ["parcel_depot"], "zone_id": [1], "operator": ["post"]},
        geometry=[Point(0.5, 0.5)], crs=CRS,
    ).to_file("facilities.gpkg")
    _csv("parcel_attributes.csv", [(2, 30), (3, 20)], ["zone_id", "jobs"])
    _csv("parcel_rates.csv", [("jobs", 0.1)], ["attribute", "rate"])
    _csv("population.csv", [(2, 100)], ["zone_id", "persons"])
    _csv("order_levels.csv", [(0, 0, 0.0), (1, 1, None)], ["level", "quantity", "threshold"])
    _csv("order_utility.csv", [(0.0,)], ["value"])
    _csv("operator_shares.csv", [("post", 1.0)], ["operator", "share"])
    _csv("parcel_settings.csv", [("period", 10)], ["setting", "value"])
    _csv("delivery_settings.csv", [("max_load", 10)], ["setting", "value"])
    _csv("delivery_departures.csv", [(8, 0.0), (9, 1.0)], ["hour", "cumulative_share"])
    _csv("trip_attributes.csv", [(1, 5), (2, 5), (3, 5)], ["zone_id", "jobs"])
    _csv("trip_rates.csv", [("service", "jobs", 1.0)], ["segment", "attribute", "rate"])
    _csv("trip_decay.csv", [("service", 0.0, 1.0, 0.0, 1.0)], ["segment", "alpha", "beta", "cost_per_hour", "cost_per_km"])
    pairs = [(1, 2), (2, 1), (2, 3), (3, 2)]
    geopandas.GeoDataFrame(
        {"link_id": range(1, 5), "from_node": [a for a, _ in pairs], "to_node": [b for _, b in pairs], "length": 1.0,
         "road_type": "street"},
        geometry=[LineString([(a, 0), (b, 0)]) for a, b in pairs], crs=CRS,
    ).to_file("network.gpkg")
    _csv("assignment_vehicles.csv", [("van", "van", 10, 1)], ["vehicle", "speed_class", "cost_per_hour", "cost_per_km"])
    _csv("link_speeds.csv", [(i, "van", 30) for i in range(1, 5)], ["link_id", "speed_class", "speed"])
    _csv("road_costs.csv", [], ["road_type", "speed_class", "cost"])
    _csv("time_intervals.csv", [("day", 0, 24)], ["time_interval", "start", "end"])
    _csv("matrix_assignment.csv", [("service", "van", "service", 0.5, 0.1)], ["matrix", "vehicle", "segment", "utilization", "minimum"])
    _csv("emission_factors.csv", [("van", "street", "co2", 100, 200)], ["vehicle", "road_type", "pollutant", "empty", "full"])


def test_parcels_vans_loads_and_emissions_in_turn():
    _write_inputs()
    assert main(["synth", "parcel-demand"]) == 0
    assert pd.read_csv("parcel_demand.csv")["parcels"].sum() == 3 + 2 + 5
    assert main(["synth", "deliveries", "--seed", "1"]) == 0
    assert main(["synth", "deliveries", "--seed", "1", "--routing", "savings", "--force"]) == 0
    assert geopandas.read_file("delivery_tours.gpkg")["parcels"].sum() == 10
    assert main(["synth", "trip-matrices"]) == 0
    assert main(["synth", "network-loads"]) == 0
    loads = pd.read_parquet("network_loads.parquet")
    assert set(loads["segment"]) == {"parcel_deliveries", "service"}
    assert main(["synth", "network-emissions"]) == 0
    assert pd.read_parquet("network_emissions.parquet")["co2"].sum() > 0


def test_unknown_routing_is_a_usage_error():
    with pytest.raises(SystemExit):
        main(["synth", "deliveries", "--routing", "fastest"])


def test_network_loads_need_trips(capsys):
    _write_inputs()
    assert main(["synth", "network-loads"]) == 1
    assert "needs trips" in capsys.readouterr().err
