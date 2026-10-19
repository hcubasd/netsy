import os
import sys

import geopandas
import pandas as pd

from netsy.cli._output import may_write
from netsy.synth.facility_chains import facility_chains


def _read_geopackage(path):
    if not os.path.exists(path):
        raise ValueError(f"{path}: not found")
    try:
        return geopandas.read_file(path)
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError(f"{path}: {error}") from None


def _read_csv(path):
    if not os.path.exists(path):
        raise ValueError(f"{path}: not found")
    try:
        return pd.read_csv(path)
    except (OSError, ValueError) as error:
        raise ValueError(f"{path}: {error}") from None


def run(force=False):
    output = "transaction_legs.gpkg"
    if not may_write(output, force):
        return 1
    try:
        transactions = _read_geopackage("desire_lines.gpkg")
        facilities = _read_geopackage("facilities.gpkg")
        steps = _read_csv("facility_chain_steps.csv")
        legs = facility_chains(transactions, facilities, steps)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    legs.to_file(output, driver="GPKG")
    return 0
