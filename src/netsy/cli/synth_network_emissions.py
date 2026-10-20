import os
import sys

import geopandas
import pandas as pd

from netsy.cli._output import may_write
from netsy.synth.network_emissions import emissions_by_copert, emissions_by_factors

# The tables each method reads besides network_loads.csv and network.gpkg.
METHOD_TABLES = {
    "factors": ("emission_factors.csv",),
    "copert": ("copert_vehicles.csv", "copert_v_coefficients.csv", "non_exhaust_factors.csv"),
}


def _read(path):
    if not os.path.exists(path):
        raise ValueError(f"{path}: not found")
    try:
        if path.endswith(".gpkg"):
            return geopandas.read_file(path, ignore_geometry=True)
        return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError(f"{path}: {error}") from None


def run(force=False, method="factors"):
    output = "network_emissions.csv"
    if not may_write(output, force):
        return 1
    try:
        frames = [_read("network_loads.csv"), _read("network.gpkg")] + [_read(path) for path in METHOD_TABLES[method]]
        table = (emissions_by_factors if method == "factors" else emissions_by_copert)(*frames)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    table.to_csv(output, index=False, float_format="%.6g")
    return 0
