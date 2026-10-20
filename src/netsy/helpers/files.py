import os

import geopandas
import pandas as pd

from netsy.helpers import validate
from netsy.helpers.validate import check_agents, check_size_classes, check_size_totals, check_zones


def _checked(path, table, check):
    try:
        result = check(table)
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from None
    return table if result is None else result


def _read_csv(path):
    # Every cell is read as text, so a key such as a zone id compares the
    # same in every table; only an empty cell is missing, since strings such
    # as "NA" are legitimate key values. Each table's check converts its own
    # value columns to numbers.
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    except FileNotFoundError:
        raise ValueError(f"{path}: not found") from None


def _read_geopackage(path):
    if not os.path.exists(path):
        raise ValueError(f"{path}: not found")
    try:
        return geopandas.read_file(path)
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError(f"{path}: {error}") from None


def read_zones(path):
    """The zones at `path` as a GeoDataFrame, validated. Raises ValueError,
    prefixed with the path, if the file is missing or malformed.
    """
    return _checked(path, _read_geopackage(path), check_zones)


def read_size_totals(path):
    """The size total of each stratum at `path`, validated."""
    return _checked(path, _read_csv(path), check_size_totals)


def read_size_classes(path):
    """The size classes of each agent class at `path`, validated."""
    return _checked(path, _read_csv(path), check_size_classes)


def read_agents(path):
    """The agents at `path` as a GeoDataFrame, validated. Raises ValueError,
    prefixed with the path, if the file is missing or malformed.
    """
    return _checked(path, _read_geopackage(path), check_agents)


def read_facilities(path):
    """The facilities at `path` as a GeoDataFrame, validated."""
    return _checked(path, _read_geopackage(path), validate.check_facilities)


# The tables shipments reads, by file name, with the check of each.
SHIPMENT_TABLES = {
    "production_rates.csv": validate.check_rates,
    "consumption_rates.csv": validate.check_rates,
    "shipment_totals.csv": validate.check_shipment_totals,
    "flow_types.csv": validate.check_flow_types,
    "distance_decay.csv": validate.check_distance_decay,
    "shipment_sizes.csv": validate.check_shipment_sizes,
    "shipment_vehicles.csv": validate.check_shipment_vehicles,
    "vehicle_choice.csv": lambda table: validate.check_choice(table, "vehicle"),
    "delivery_windows.csv": validate.check_delivery_windows,
    "delivery_choice.csv": lambda table: validate.check_choice(table, "window"),
}


def read_table(path):
    """The shipment input table at `path`, validated by its file name."""
    return _checked(path, _read_csv(path), SHIPMENT_TABLES[os.path.basename(path)])
