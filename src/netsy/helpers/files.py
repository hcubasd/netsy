import os

import geopandas
import pandas as pd

from netsy.helpers.validate import check_distribution, check_effects, check_thresholds, check_zones


def _read(path, dtype):
    # Only an empty cell is missing: strings such as "NA" are legitimate
    # stratum values, and stratum values are always read as text so a numeric
    # zone_id does not change type depending on its sibling dimensions.
    try:
        return pd.read_csv(path, dtype=dtype, keep_default_na=False, na_values=[""])
    except FileNotFoundError:
        raise ValueError(f"{path}: not found") from None


def _checked(path, table, check):
    try:
        check(table)
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from None
    return table


def read_effects(path):
    """The effects table at `path`, validated. Raises ValueError, prefixed
    with the path, if the file is missing or malformed.
    """
    table = _read(path, {"stratum": str, "stratum_value": str})
    return _checked(path, table, check_effects)


def read_thresholds(path):
    """The thresholds table at `path`, validated. Raises ValueError, prefixed
    with the path, if the file is missing or malformed.
    """
    table = _read(path, {"resource": str})
    return _checked(path, table, check_thresholds)


def read_aggregate(path):
    """A supply or demand table at `path`, all text. Which columns are strata
    and which are resources is only known once capacities and needs are
    read, so converting the resource columns to numbers is left to
    `combine_agent_inputs`.
    """
    return _read(path, str)


def read_distribution(path):
    """The capacities or needs table at `path`, validated, with whole-number
    levels and float probabilities. Raises ValueError, prefixed with the
    path, if the file is missing or malformed.
    """
    table = _read(path, str)
    try:
        for column in ("resource_level", "probability"):
            if column in table.columns:
                table[column] = pd.to_numeric(table[column])
        levels = table.get("resource_level")
        if levels is not None and pd.api.types.is_float_dtype(levels) and (levels.dropna() % 1 == 0).all() and not levels.isna().any():
            table["resource_level"] = levels.astype("int64")
    except (ValueError, TypeError):
        raise ValueError(f"{path}: 'resource_level' and 'probability' must be numbers") from None
    return _checked(path, table, check_distribution)


def read_zones(path):
    """The zones at `path` as a GeoDataFrame, validated. Raises ValueError,
    prefixed with the path, if the file is missing or malformed.
    """
    if not os.path.exists(path):
        raise ValueError(f"{path}: not found")
    try:
        zones = geopandas.read_file(path)
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError(f"{path}: {error}") from None
    return _checked(path, zones, check_zones)
