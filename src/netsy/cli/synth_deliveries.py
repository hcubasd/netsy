import sys

import numpy as np
import pandas as pd

from netsy.cli._output import may_write
from netsy.helpers.files import read_zones
from netsy.helpers.skims import read_skims
from netsy.synth.deliveries import deliveries


def _read(path):
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    except FileNotFoundError:
        raise ValueError(f"{path}: not found") from None


def run(force=False, seed=None, routing="massgt"):
    output = "delivery_tours.gpkg"
    if not may_write(output, force):
        return 1
    try:
        table = deliveries(
            read_zones("zones.gpkg"), read_skims("skims.omx"), _read("parcel_demand.csv"),
            _read("delivery_settings.csv"), _read("delivery_departures.csv"), np.random.default_rng(seed), routing,
        )
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    table.to_file(output, driver="GPKG")
    return 0
