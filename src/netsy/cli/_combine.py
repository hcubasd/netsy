import os
import sys

from netsy.helpers.files import read_effects, read_thresholds


def run_combiner(*, effects, thresholds, output, combine, force):
    """Read the `effects` and `thresholds` files, write `combine` of them to
    `output`, and return the process exit code. Refuses to replace an
    existing `output` unless `force`, so a stale file is never silently kept
    and a hand-edited one is never silently lost.
    """
    if os.path.exists(output) and not force:
        print(f"{output}: already exists (pass --force to overwrite)", file=sys.stderr)
        return 1
    try:
        table = combine(read_effects(effects), read_thresholds(thresholds))
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    table.to_csv(output, index=False)
    return 0
