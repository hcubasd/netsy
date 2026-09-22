import os
import sys


def may_write(output, force):
    """Whether `output` can be written. Refuses to replace an existing file
    unless `force`, so a stale file is never silently kept and a hand-edited
    one is never silently lost; says why on stderr when it refuses.
    """
    if os.path.exists(output) and not force:
        print(f"{output}: already exists (pass --force to overwrite)", file=sys.stderr)
        return False
    return True
