import os

import geopandas

from netsy.helpers.validate import check_agents


def _checked(path, table, check):
    try:
        check(table)
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from None
    return table


def read_agents(path):
    """The agents at `path` as a GeoDataFrame, validated. Raises ValueError,
    prefixed with the path, if the file is missing or malformed.
    """
    if not os.path.exists(path):
        raise ValueError(f"{path}: not found")
    try:
        agents = geopandas.read_file(path)
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError(f"{path}: {error}") from None
    return _checked(path, agents, check_agents)
