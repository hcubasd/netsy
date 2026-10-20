import sys

import numpy as np

from netsy.cli._output import may_write
from netsy.helpers.files import read_size_classes, read_size_totals, read_zones
from netsy.synth.agents import agents


def run(force=False, seed=None, min_size=0):
    output = "agents.gpkg"
    if not may_write(output, force):
        return 1
    try:
        table = agents(
            read_zones("zones.gpkg"),
            read_size_totals("size_totals.csv"),
            read_size_classes("size_classes.csv"),
            np.random.default_rng(seed),
            min_size,
        )
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    table.to_file(output, driver="GPKG")
    return 0
