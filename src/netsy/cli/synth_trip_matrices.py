import sys

import pandas as pd

from netsy.cli._output import may_write
from netsy.helpers.files import read_zones
from netsy.helpers.skims import read_skims, write_matrices
from netsy.synth.trip_matrices import trip_matrices


def _read(path):
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    except FileNotFoundError:
        raise ValueError(f"{path}: not found") from None


def run(force=False):
    output = "trip_matrices.omx"
    if not may_write(output, force):
        return 1
    try:
        skims = read_skims("skims.omx")
        matrices = trip_matrices(
            read_zones("zones.gpkg"), skims, _read("trip_attributes.csv"), _read("trip_rates.csv"), _read("trip_decay.csv"),
        )
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    write_matrices(output, skims[0], matrices)
    return 0
