import numpy as np
import shapely


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
