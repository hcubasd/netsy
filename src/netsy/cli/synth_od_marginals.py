import os
import sys

import pandas as pd

from netsy.cli._output import may_write
from netsy.synth.od_marginals import od_marginals


def _read(path):
    if not os.path.exists(path):
        raise ValueError(f"{path}: not found")
    try:
        return pd.read_csv(path)
    except (OSError, ValueError) as error:
        raise ValueError(f"{path}: {error}") from None


def run(force=False):
    outputs = ("productions.csv", "attractions.csv")
    if not all(may_write(output, force) for output in outputs):
        return 1
    try:
        productions, attractions = od_marginals(
            _read("location_attributes.csv"), _read("marginal_coefficients.csv"), _read("od_prior.csv"),
        )
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    productions.to_csv("productions.csv", index=False)
    attractions.to_csv("attractions.csv", index=False)
    return 0
