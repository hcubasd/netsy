import pandas as pd

from netsy.helpers.validate import check_effects, check_thresholds


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
