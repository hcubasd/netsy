"""Synthesize agents from stratum size totals, as MASS-GT's firm synthesis
does, generalized to any strata.

Every stratum (a zone and any other dimensions) has a total size, such as
its jobs. Agents are drawn one at a time from the size classes of their
agent class until that total is used up, with MASS-GT's rules: a size
uniformly within a closed class, a triangular draw that follows what is left
for an open class, and a draw kept unless it exceeds what is left by more
than 30%, in which case the agent takes exactly what is left. Agents below a
minimum size are then dropped, and the rest placed uniformly in their zone.
What an agent produces and consumes follows from its size and agent class
later, when shipments are drawn.
"""

import geopandas
import numpy as np
import pandas as pd

from netsy.helpers.sampling import sample_points
from netsy.helpers.validate import SIZE_CLASS_OPTIONAL, SIZE_CLASS_VALUES, SIZE_TOTAL_VALUES

# A draw is kept unless it exceeds what is left of the stratum by more than
# this factor (MASS-GT's firm synthesis).
OVERSHOOT = 1.3


def _zone_key(value):
    # A zone id compares as text, whether it came from a CSV or a geopackage.
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def _keys(table, values, strata, name):
    """The key columns of `table`, which must all be stratum columns."""
    keys = [column for column in table.columns if column not in values]
    extra = sorted(set(keys) - set(strata))
    if extra:
        raise ValueError(f"{name}: columns {extra} are not stratum columns of size_totals.csv")
    return keys


def _sizes(total, classes, rng):
    """Agent sizes drawn until `total` is used up, as MASS-GT draws firms:
    a class by its probability; then, for a closed class, a whole size
    uniformly within its bounds, or, for an open class (no `size_max`), a
    whole size from a triangular distribution from `size_min` through a mode
    of half of what is left (at least `size_min`) to one and a half times
    what is left (at least `size_median`). A size more than 30% above what is
    left becomes exactly what is left.
    """
    lows, highs, medians, probabilities = classes
    sizes, remaining = [], float(total)
    while remaining > 0:
        index = rng.choice(len(lows), p=probabilities)
        if np.isnan(highs[index]):
            low = lows[index]
            size = float(round(rng.triangular(low, max(low, remaining / 2), max(medians[index], 1.5 * remaining))))
        else:
            size = float(rng.integers(int(lows[index]), int(highs[index]) + 1))
        if size > OVERSHOOT * remaining:
            size = remaining
        sizes.append(size)
        remaining -= size
    return sizes


def agents(zones, size_totals, size_classes, rng, min_size=0):
    """One row per synthesized agent: `agent_id`, its stratum columns, its
    `size`, and a point `geometry` placed uniformly in its zone. The number
    of agents is where each stratum's size total runs out, not an input;
    agents smaller than `min_size` are then dropped, and their size is not
    given to others. `rng` is a numpy Generator, so a seeded one makes the
    result repeatable. Raises ValueError if the tables do not fit together.
    """
    strata = [column for column in size_totals.columns if column not in SIZE_TOTAL_VALUES]
    class_keys = _keys(size_classes, SIZE_CLASS_VALUES + SIZE_CLASS_OPTIONAL, strata, "size_classes.csv")

    classes = {}
    for key, group in size_classes.groupby(class_keys, sort=False) if class_keys else [((), size_classes)]:
        key = key if isinstance(key, tuple) else (key,)
        probabilities = group["probability"].to_numpy(dtype=float)
        medians = group["size_median"] if "size_median" in group.columns else pd.Series(np.nan, index=group.index)
        classes[key] = (
            group["size_min"].to_numpy(dtype=float), group["size_max"].to_numpy(dtype=float),
            medians.to_numpy(dtype=float), probabilities / probabilities.sum(),
        )

    polygons = {_zone_key(zone): geometry for zone, geometry in zip(zones["zone_id"], zones.geometry)}
    missing = sorted({_zone_key(zone) for zone in size_totals["zone_id"]} - set(polygons))
    if missing:
        raise ValueError(f"size_totals.csv: zones {missing[:5]}{'...' if len(missing) > 5 else ''} are not in zones.gpkg")

    rows, sizes = [], []
    for row in size_totals.to_dict("records"):
        if row["size"] <= 0:
            continue
        key = tuple(row[column] for column in class_keys)
        if key not in classes:
            raise ValueError(f"size_classes.csv: no size classes for {dict(zip(class_keys, key))}")
        drawn = _sizes(row["size"], classes[key], rng)
        rows.extend([[row[column] for column in strata]] * len(drawn))
        sizes.extend(drawn)
    table = pd.DataFrame(rows, columns=strata)
    table["size"] = sizes
    # A class may start at zero, as MASS-GT's smallest firms do; an agent of
    # size zero is not an agent.
    table = table[(table["size"] > 0) & (table["size"] >= min_size)].reset_index(drop=True)
    if table.empty:
        raise ValueError("size_totals.csv: no agent of at least the minimum size could be made")

    table.insert(0, "agent_id", range(1, len(table) + 1))
    xs, ys = np.empty(len(table)), np.empty(len(table))
    for zone, positions in table.groupby(table["zone_id"].map(_zone_key)).indices.items():
        xs[positions], ys[positions] = sample_points(polygons[zone], len(positions), rng)
    return geopandas.GeoDataFrame(table, geometry=geopandas.points_from_xy(xs, ys), crs=zones.crs)
