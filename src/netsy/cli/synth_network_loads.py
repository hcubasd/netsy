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


def run(force=False, payload_strata=False):
    output = "network_loads.parquet"
    if not may_write(output, force):
        return 1
    try:
        trips = {path: _read(path) for path in TRIP_TABLES if os.path.exists(path)}
        matrices = read_matrices("trip_matrices.omx") if os.path.exists("trip_matrices.omx") else None
        if not trips and matrices is None:
            raise ValueError("network-loads needs trips: tours.gpkg, delivery_tours.gpkg or trip_matrices.omx")
        settings = {}
        if os.path.exists("assignment_settings.csv"):
            values = _read("assignment_settings.csv").set_index("setting")["value"].to_dict()
            unknown = set(values) - {"route_samples", "seed", "jitter"}
            if unknown: raise ValueError(f"assignment_settings.csv: unknown settings {sorted(unknown)}")
            settings = {k: float(v) if k == "jitter" else int(v) for k, v in values.items()}
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            table = network_loads(
                _read("network.gpkg"), read_zones("zones.gpkg"), *(_read(path) for path in TABLES), trips, matrices,
                _read("matrix_assignment.csv") if matrices is not None else None, workers=int(os.environ.get("NETSY_WORKERS", min(os.cpu_count() or 1, 4))), payload_strata=payload_strata, **settings,
            )
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    for warning in caught:
        print(f"warning: {warning.message}", file=sys.stderr)
    table.to_parquet(output, index=False)
    return 0
