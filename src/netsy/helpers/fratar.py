"""FRATAR balancing of a dense matrix, with MASS-GT's stopping rules."""

import numpy as np


def fratar(matrix, rows, columns, tolerance, max_iterations, decimals=None, stop_on_stall=False):
    """`matrix` scaled in place, each iteration first every column to its
    total in `columns` and then every row to its total in `rows`, so its rows
    match. An iteration's convergence is the larger distance from one of the
    two passes' largest scaling factors (rounded to `decimals`, if given);
    it stops below `tolerance`, after `max_iterations`, or, with
    `stop_on_stall`, when the convergence repeats. Returns the matrix and
    the last convergence.
    """
    previous, convergence = None, None
    for _ in range(max_iterations):
        factors = []
        for axis, targets in ((0, columns), (1, rows)):
            totals = matrix.sum(axis=axis)
            scale = np.divide(targets, totals, out=np.ones_like(totals, dtype=float), where=totals > 0)
            if axis == 0:
                matrix *= scale[None, :]
            else:
                matrix *= scale[:, None]
            used = scale[totals > 0]
            factors.append(used[np.argmax(np.abs(used))] if len(used) else 0.0)
        convergence = max(abs(factors[0] - 1), abs(factors[1] - 1))
        if decimals is not None:
            convergence = round(convergence, decimals)
        if convergence <= tolerance or (stop_on_stall and convergence == previous):
            break
        previous = convergence
    return matrix, convergence
