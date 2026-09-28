import sys

import numpy as np

from netsy.cli._output import may_write
from netsy.helpers.files import read_agents
from netsy.synth.desire_lines import desire_lines


def run(force=False, seed=None):
    output = "desire_lines.gpkg"
    if not may_write(output, force):
        return 1
    try:
        table = desire_lines(read_agents("agents.gpkg"), np.random.default_rng(seed))
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    table.to_file(output, driver="GPKG")
    return 0
