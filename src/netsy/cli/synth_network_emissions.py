import os
import sys

import geopandas
import pandas as pd

from netsy.cli._output import may_write
from netsy.helpers.geometry import kilometers
from netsy.synth.network_emissions import GRADIENT_BINS, PAYLOAD_BINS, network_emissions


_INPUTS = {
    "network_loads.csv": ("link_id", "time_interval", "resource", "vehicle", "forward", "vehicle_count", "velocity", "load_pct"),
    "network.gpkg": ("link_id", "grade"),
    "vehicles.csv": ("vehicle", "vehicle_type"),
    "copert_v_coefficients.csv": (
        "vehicle_type", "pollutant", "gradient_bin", "payload_bin",
        "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "rf",
    ),
    "emission_factors.csv": ("vehicle_type", "pollutant", "emission_factor"),
}

_OUTPUT_COLUMNS = [
    "link_id", "time_interval", "resource", "vehicle", "forward", "pollutant", "source", "grams",
]


def _read(path):
    if not os.path.exists(path):
        raise ValueError(f"{path}: not found")
    try:
        return geopandas.read_file(path) if path.endswith(".gpkg") else pd.read_csv(path)
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError(f"{path}: {error}") from None


def _numbers(frame, path, columns, lower=None, upper=None):
    for column in columns:
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.isna().any() or (lower is not None and (values < lower).any()) or (upper is not None and (values > upper).any()):
            raise ValueError(f"{path}: '{column}' has values outside its valid range")


def _validate(frames):
    for path, columns in _INPUTS.items():
        missing = [column for column in columns if column not in frames[path].columns]
        if missing:
            raise ValueError(f"{path}: missing columns {missing}")
    network = frames["network.gpkg"]
    if network.crs is None or network.geometry.isna().any() or not network.geometry.geom_type.eq("LineString").all():
        raise ValueError("network.gpkg: needs a CRS and line geometries")
    if network["link_id"].duplicated().any():
        raise ValueError("network.gpkg: 'link_id' values must be unique")
    _numbers(network, "network.gpkg", ("grade",))
    loads = frames["network_loads.csv"]
    _numbers(loads, "network_loads.csv", ("vehicle_count", "velocity", "load_pct"), 0)
    if (pd.to_numeric(loads["vehicle_count"]) == 0).any() or (pd.to_numeric(loads["load_pct"]) > 1).any():
        raise ValueError("network_loads.csv: counts must be positive and load_pct must be at most one")
    coefficients = frames["copert_v_coefficients.csv"]
    _numbers(coefficients, "copert_v_coefficients.csv", ("alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta"))
    _numbers(coefficients, "copert_v_coefficients.csv", ("rf",), 0, 1)
    if not coefficients["gradient_bin"].isin(GRADIENT_BINS).all() or not coefficients["payload_bin"].isin(PAYLOAD_BINS).all():
        raise ValueError("copert_v_coefficients.csv: gradient_bin or payload_bin is not a COPERT V bin")
    if coefficients.duplicated(["vehicle_type", "pollutant", "gradient_bin", "payload_bin"]).any():
        raise ValueError("copert_v_coefficients.csv: coefficient keys must be unique")
    factors = frames["emission_factors.csv"]
    _numbers(factors, "emission_factors.csv", ("emission_factor",), 0)
    if factors.duplicated(["vehicle_type", "pollutant"]).any():
        raise ValueError("emission_factors.csv: factor keys must be unique")


def run(force=False):
    if not may_write("network_emissions.csv", force):
        return 1
    try:
        frames = {path: _read(path) for path in _INPUTS}
        _validate(frames)
        frames["network.gpkg"] = kilometers(frames["network.gpkg"], "network.gpkg")
        rows = network_emissions(*(frames[path].to_dict("records") for path in _INPUTS))
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    pd.DataFrame(rows, columns=_OUTPUT_COLUMNS).to_csv("network_emissions.csv", index=False)
    return 0
