import os
import sys

import pandas as pd

from netsy.cli._output import may_write
from netsy.synth.od_flows import od_flows


def _read(path):
    if not os.path.exists(path):
        raise ValueError(f"{path}: not found")
    try:
        return pd.read_csv(path)
    except (OSError, ValueError) as error:
        raise ValueError(f"{path}: {error}") from None


def run(force=False):
    output = "od_flows.csv"
    if not may_write(output, force):
        return 1
    try:
        flows = od_flows(
            _read("productions.csv"),
            _read("attractions.csv"),
            _read("od_prior.csv"),
        )
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    flows.to_csv(output, index=False)
    return 0
