import os
import sys
import warnings

import geopandas
import numpy as np
import pandas as pd

from netsy.cli._output import may_write
from netsy.helpers.geometry import kilometers
from netsy.synth.network_loads import network_loads


_INPUTS = {
    "network.gpkg": ("link_id", "grade", "road_type", "oneway"),
    "departures.csv": ("resource", "time_interval", "probability"),
    "time_intervals.csv": ("time_interval", "duration"),
    "dwell_times.csv": ("resource", "dwell_time"),
    "vehicles.csv": ("vehicle", "bpr_alpha", "bpr_beta", "time_coefficient", "distance_coefficient", "pcu"),
    "vehicle_velocities.csv": ("vehicle", "road_type", "velocity"),
    "vehicle_capacities.csv": ("vehicle", "resource", "capacity"),
    "road_capacities.csv": ("road_type", "capacity"),
    "alternative_specific_constants.csv": ("vehicle", "resource", "alternative_specific_constant"),
}
_TRANSACTION_COLUMNS = ("resource", "quantity", "origin_agent_id")

_OUTPUT_COLUMNS = [
    "link_id", "time_interval", "resource", "vehicle", "forward", "vehicle_count", "velocity", "load_pct",
]


def _read(path):
    if not os.path.exists(path):
        raise ValueError(f"{path}: not found")
    try:
        return geopandas.read_file(path) if path.endswith(".gpkg") else pd.read_csv(path)
    except FileNotFoundError:
        raise ValueError(f"{path}: not found") from None
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError(f"{path}: {error}") from None


def _require(frame, path):
    missing = [column for column in _INPUTS[path] if column not in frame.columns]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}")


def _validate(frames, transaction_path):
    for path, frame in frames.items():
        if path == "transactions":
            continue
        _require(frame, path)
    transactions = frames["transactions"]
    missing = [column for column in _TRANSACTION_COLUMNS if column not in transactions.columns]
    if missing:
        raise ValueError(f"{transaction_path}: missing columns {missing}")
    if "load_pct" in frames["dwell_times.csv"].columns:
        raise ValueError("dwell_times.csv: 'load_pct' was removed; returns are empty")
    network = frames["network.gpkg"]
    if network.crs is None or transactions.crs is None or network.crs != transactions.crs:
        raise ValueError(f"network.gpkg and {transaction_path}: both need the same CRS")
    if network.geometry.isna().any() or not network.geometry.geom_type.eq("LineString").all():
        raise ValueError("network.gpkg: every geometry must be a line")
    if transactions.geometry.isna().any() or not transactions.geometry.geom_type.eq("LineString").all():
        raise ValueError(f"{transaction_path}: every geometry must be a line")
    if network["link_id"].duplicated().any():
        raise ValueError("network.gpkg: 'link_id' values must be unique")
    quantities = pd.to_numeric(transactions["quantity"], errors="coerce")
    if (quantities.isna() | (quantities <= 0) | (quantities % 1 != 0)).any():
        raise ValueError(f"{transaction_path}: 'quantity' must contain positive whole numbers")
    durations = pd.to_numeric(frames["time_intervals.csv"]["duration"], errors="coerce")
    if frames["time_intervals.csv"]["time_interval"].duplicated().any() or durations.isna().any() or (durations <= 0).any():
        raise ValueError("time_intervals.csv: intervals must be unique and durations positive")
    dwell_times = pd.to_numeric(frames["dwell_times.csv"]["dwell_time"], errors="coerce")
    if dwell_times.isna().any() or (dwell_times < 0).any():
        raise ValueError("dwell_times.csv: 'dwell_time' must be zero or more")
    capacities = pd.to_numeric(frames["vehicle_capacities.csv"]["capacity"], errors="coerce")
    if capacities.isna().any() or (capacities <= 0).any() or (capacities % 1 != 0).any():
        raise ValueError("vehicle_capacities.csv: 'capacity' must contain positive whole numbers")
    for path, column in (
        ("departures.csv", "probability"), ("vehicle_velocities.csv", "velocity"),
        ("road_capacities.csv", "capacity"), ("vehicles.csv", "pcu"),
    ):
        values = pd.to_numeric(frames[path][column], errors="coerce")
        if values.isna().any() or (values < 0).any() or (path != "departures.csv" and (values == 0).any()):
            raise ValueError(f"{path}: '{column}' must contain valid non-negative numbers")
    for column in ("bpr_alpha", "bpr_beta"):
        values = pd.to_numeric(frames["vehicles.csv"][column], errors="coerce")
        if values.isna().any() or (values < 0).any():
            raise ValueError(f"vehicles.csv: '{column}' must contain non-negative numbers")
    for column in ("time_coefficient", "distance_coefficient"):
        values = pd.to_numeric(frames["vehicles.csv"][column], errors="coerce")
        if values.isna().any() or (values > 0).any():
            raise ValueError(f"vehicles.csv: '{column}' must contain non-positive numbers")


def run(force=False, seed=None, transactions=None):
    if not may_write("network_loads.csv", force):
        return 1
    try:
        frames = {path: _read(path) for path in _INPUTS}
        transaction_path = transactions or "desire_lines.gpkg"
        frames["transactions"] = _read(transaction_path)
        _validate(frames, transaction_path)
        metric_crs = frames["network.gpkg"].estimate_utm_crs() if frames["network.gpkg"].crs.is_geographic else frames["network.gpkg"].crs
        frames["network.gpkg"] = kilometers(frames["network.gpkg"], "network.gpkg", metric_crs)
        frames["transactions"] = kilometers(frames["transactions"], transaction_path, metric_crs)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            rows = network_loads(
                frames["network.gpkg"].to_dict("records"),
                frames["transactions"].to_dict("records"),
                *(frames[path].to_dict("records") for path in _INPUTS if path != "network.gpkg"),
                rng=np.random.default_rng(seed),
            )
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    for warning in caught:
        print(f"warning: {warning.message}", file=sys.stderr)
    pd.DataFrame(rows, columns=_OUTPUT_COLUMNS).to_csv("network_loads.csv", index=False)
    return 0
