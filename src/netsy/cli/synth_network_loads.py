import os
import sys
import warnings

import geopandas
import pandas as pd

from netsy.cli._output import may_write
from netsy.helpers.files import read_zones
from netsy.helpers.skims import read_matrices
from netsy.synth.network_loads import network_loads

TABLES = ("assignment_vehicles.csv", "link_speeds.csv", "road_costs.csv", "time_intervals.csv")
# Trip sources, each read when present.
TRIP_TABLES = ("tours.gpkg", "delivery_tours.gpkg")


def _read(path):
    if not os.path.exists(path):
        raise ValueError(f"{path}: not found")
    try:
        if path.endswith(".gpkg"):
            return geopandas.read_file(path, ignore_geometry=True) if path in TRIP_TABLES else geopandas.read_file(path)
        return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError(f"{path}: {error}") from None


def run(force=False):
    output = "network_loads.csv"
    if not may_write(output, force):
        return 1
    try:
        trips = {path: _read(path) for path in TRIP_TABLES if os.path.exists(path)}
        matrices = read_matrices("trip_matrices.omx") if os.path.exists("trip_matrices.omx") else None
        if not trips and matrices is None:
            raise ValueError("network-loads needs trips: tours.gpkg, delivery_tours.gpkg or trip_matrices.omx")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            table = network_loads(
                _read("network.gpkg"), read_zones("zones.gpkg"), *(_read(path) for path in TABLES), trips, matrices,
                _read("matrix_assignment.csv") if matrices is not None else None, workers=os.cpu_count() or 1,
            )
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    for warning in caught:
        print(f"warning: {warning.message}", file=sys.stderr)
    table.to_csv(output, index=False, float_format="%.6g")
    return 0
