import sys

import pandas as pd

from netsy.cli._output import may_write
from netsy.helpers.files import read_facilities, read_zones
from netsy.helpers.skims import read_skims
from netsy.synth.parcel_demand import parcel_demand

TABLES = (
    "parcel_attributes.csv", "parcel_rates.csv", "population.csv", "order_levels.csv", "order_utility.csv",
    "operator_shares.csv", "parcel_settings.csv",
)


def _read(path):
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    except FileNotFoundError:
        raise ValueError(f"{path}: not found") from None


def run(force=False):
    output = "parcel_demand.csv"
    if not may_write(output, force):
        return 1
    try:
        table = parcel_demand(
            read_zones("zones.gpkg"), read_facilities("facilities.gpkg"), read_skims("skims.omx"),
            *(_read(path) for path in TABLES),
        )
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    table.to_csv(output, index=False)
    return 0
