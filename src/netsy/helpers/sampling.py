import numpy as np
import shapely


def truncated_draw(levels, cumulative, budget, rng):
    """One level drawn from a distribution restricted to the levels that
    do not exceed `budget`, renormalized. `levels` is ascending and
    `cumulative` the running sum of its probabilities. Returns None when no
    feasible level has any probability left: nothing can be drawn, and the
    caller must not invent a value the distribution does not support.
    """
    feasible = int(np.searchsorted(levels, budget, side="right"))
    if feasible == 0:
        return None
    total = cumulative[feasible - 1]
    if total <= 0:
        return None
    index = int(np.searchsorted(cumulative[:feasible], rng.random() * total, side="right"))
    return int(levels[min(index, feasible - 1)])


def sample_points(polygon, count, rng):
    """`count` points drawn uniformly inside `polygon` as (x, y) arrays, by
    drawing in its bounding box and keeping the points that fall inside.
    """
    minx, miny, maxx, maxy = polygon.bounds
    box_area = (maxx - minx) * (maxy - miny)
    if polygon.is_empty or polygon.area <= 0 or box_area <= 0:
        raise ValueError("a zone has no area to place agents in")
    acceptance = polygon.area / box_area

    xs, ys, found = [], [], 0
    while found < count:
        batch = min(int(1.5 * (count - found) / acceptance) + 64, 1_000_000)
        x = rng.uniform(minx, maxx, batch)
        y = rng.uniform(miny, maxy, batch)
        inside = shapely.contains_xy(polygon, x, y)
        xs.append(x[inside])
        ys.append(y[inside])
        found += int(inside.sum())
    return np.concatenate(xs)[:count], np.concatenate(ys)[:count]
