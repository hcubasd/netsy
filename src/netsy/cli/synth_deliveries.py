import sys
import os

import numpy as np
import pandas as pd

from netsy.cli._output import may_write
from netsy.helpers.files import read_zones, read_facilities
from netsy.helpers.skims import read_skims
from netsy.synth.deliveries import deliveries


def _read(path):
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    except FileNotFoundError:
        raise ValueError(f"{path}: not found") from None


def run(force=False, seed=None, routing="massgt", demand="parcel_demand.csv"):
    output = "delivery_tours.gpkg"
    if not may_write(output, force):
        return 1
    try:
        table = deliveries(
            read_zones("zones.gpkg"), read_skims("skims.omx"), _read(demand),
            _read("delivery_settings.csv"), _read("delivery_departures.csv"), np.random.default_rng(seed), routing, vehicles=_read("delivery_vehicles.csv") if os.path.exists("delivery_vehicles.csv") else None,
        )
        if os.path.exists("delivery_combustion_shares.csv"):
            from netsy.helpers.combustion import tour_combustion
            zone_column = _read("combustion_settings.csv").set_index("setting").loc["zone_column", "value"]
            table = tour_combustion(table, read_zones("zones.gpkg"), read_facilities("facilities.gpkg"),
                                    _read("delivery_combustion_shares.csv"), zone_column,
                                    np.random.default_rng(np.random.SeedSequence(seed).spawn(1)[0]))
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    table.to_file(output, driver="GPKG")
    return 0
