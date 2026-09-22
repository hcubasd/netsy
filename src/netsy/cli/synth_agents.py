import sys
import warnings

import numpy as np

from netsy.cli._output import may_write
from netsy.helpers.files import read_aggregate, read_distribution, read_zones
from netsy.synth.agents import agents


def run(force=False, seed=None):
    output = "agents.gpkg"
    if not may_write(output, force):
        return 1
    try:
        inputs = (
            read_aggregate("supply.csv"),
            read_aggregate("demand.csv"),
            read_distribution("capacities.csv"),
            read_distribution("needs.csv"),
            read_zones("zones.gpkg"),
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            table = agents(*inputs, rng=np.random.default_rng(seed))
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    for warning in caught:
        print(f"warning: {warning.message}", file=sys.stderr)
    table.to_file(output, driver="GPKG")
    return 0
