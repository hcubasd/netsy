import pandas as pd

# The value columns of each agent-synthesis table. Every other column of a
# table is a key column naming a stratum dimension.
SIZE_TOTAL_VALUES = ("size",)
SIZE_CLASS_VALUES = ("size_min", "size_max", "probability")
SIZE_CLASS_OPTIONAL = ("size_median",)


def check_zones(zones):
    """Raise ValueError unless `zones` is a usable zones table: a unique
    `zone_id` per row and a non-empty polygon or multipolygon geometry.
    Zone ids are compared as text, so 1 and "1" are the same zone.
    """
    if "zone_id" not in zones.columns:
        raise ValueError("missing 'zone_id' column")
    if zones.empty:
        raise ValueError("must have at least one zone")
    if zones["zone_id"].isna().any():
        raise ValueError("'zone_id' must not have empty cells")
    if zones.geometry.isna().any() or zones.geometry.is_empty.any():
        raise ValueError("every zone needs a geometry")
    if not zones.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise ValueError("zone geometries must be polygons")
    if zones["zone_id"].astype(str).duplicated().any():
        raise ValueError("'zone_id' values must be unique")


def _numbers(table, columns, minimum=0.0, whole=False):
    """`table` with `columns` converted to numbers, every one present and at
    least `minimum` (and whole, if asked).
    """
    table = table.copy()
    for column in columns:
        values = pd.to_numeric(table[column], errors="coerce")
        if values.isna().any() or (values < minimum).any() or (whole and (values % 1 != 0).any()):
            kind = "whole numbers" if whole else "numbers"
            raise ValueError(f"'{column}' must hold {kind} of at least {minimum:g} in every row")
        table[column] = values
    return table


def check_size_totals(table):
    """`size_totals.csv` with its sizes as numbers: one row per stratum,
    `zone_id` among the stratum columns, and the stratum's total size.
    """
    if "size" not in table.columns:
        raise ValueError("missing columns ['size']")
    if table.empty:
        raise ValueError("must have at least one row")
    strata = [column for column in table.columns if column not in SIZE_TOTAL_VALUES]
    if "zone_id" not in strata:
        raise ValueError("missing 'zone_id' column")
    if table[strata].isna().any().any():
        raise ValueError(f"stratum columns {strata} must not have empty cells")
    if table.duplicated(strata).any():
        raise ValueError("each stratum may appear only once")
    return _numbers(table, SIZE_TOTAL_VALUES)


def check_size_classes(table):
    """`size_classes.csv` with its values as numbers: per agent class (any
    stratum columns), whole-number size bounds of at least zero and class
    probabilities summing to one. A class with an empty `size_max` is open:
    it needs a `size_median` above its `size_min`.
    """
    keys = [column for column in table.columns if column not in SIZE_CLASS_VALUES + SIZE_CLASS_OPTIONAL]
    missing = [column for column in SIZE_CLASS_VALUES if column not in table.columns]
    if missing:
        raise ValueError(f"missing columns {missing}")
    if table.empty:
        raise ValueError("must have at least one row")
    if keys and table[keys].isna().any().any():
        raise ValueError(f"key columns {keys} must not have empty cells")
    table = _numbers(table, ("size_min",), minimum=0, whole=True)
    table = _numbers(table, ("probability",))
    open_classes = table["size_max"].isna()
    table["size_max"] = pd.to_numeric(table["size_max"], errors="coerce")
    closed = table.loc[~open_classes, "size_max"]
    if closed.isna().any() or (closed % 1 != 0).any():
        raise ValueError("'size_max' must hold whole numbers, or be empty for an open class")
    if (table["size_max"] < table["size_min"]).any():
        raise ValueError("'size_max' must be at least 'size_min'")
    if open_classes.any():
        if "size_median" not in table.columns:
            raise ValueError("an open class (empty 'size_max') needs a 'size_median' column")
        medians = pd.to_numeric(table.loc[open_classes, "size_median"], errors="coerce")
        if medians.isna().any() or (medians <= table.loc[open_classes, "size_min"]).any():
            raise ValueError("an open class needs a 'size_median' above its 'size_min'")
        table["size_median"] = pd.to_numeric(table["size_median"], errors="coerce")
    groups = table.groupby(keys) if keys else [((), table)]
    for _, group in groups:
        if abs(group["probability"].sum() - 1) > 1e-6:
            raise ValueError("the probabilities of each agent class must sum to one")
        drawable = (group["probability"] > 0) & (group["size_max"].isna() | (group["size_max"] > 0))
        if not drawable.any():
            raise ValueError("each agent class needs a class that can draw a size above zero")
    return table


def check_agents(agents):
    """Raise ValueError unless `agents` has unique identifiers, point
    locations, and paired whole-number production/consumption resource
    columns. Empty resource values are permitted: they mean that agent does
    not take part in that resource.
    """
    if "agent_id" not in agents.columns:
        raise ValueError("missing 'agent_id' column")
    if agents.empty:
        raise ValueError("must have at least one row")
    if agents["agent_id"].isna().any() or agents["agent_id"].duplicated().any():
        raise ValueError("'agent_id' values must be present and unique")
    if agents.crs is None:
        raise ValueError("missing CRS")
    if agents.geometry.isna().any() or agents.geometry.is_empty.any():
        raise ValueError("every agent needs a geometry")
    if not agents.geometry.geom_type.eq("Point").all():
        raise ValueError("agent geometries must be points")

    production = {column[:-len("_production")] for column in agents.columns if column.endswith("_production")}
    consumption = {column[:-len("_consumption")] for column in agents.columns if column.endswith("_consumption")}
    if not production:
        raise ValueError("must have at least one paired production and consumption resource")
    if production != consumption:
        raise ValueError("every resource must have both '_production' and '_consumption' columns")
    for resource in production:
        for suffix in ("_production", "_consumption"):
            values = pd.to_numeric(agents[f"{resource}{suffix}"], errors="coerce")
            original = agents[f"{resource}{suffix}"]
            if original.notna().ne(values.notna()).any() or ((values.dropna() < 0) | (values.dropna() % 1 != 0)).any():
                raise ValueError(f"'{resource}{suffix}' must contain whole numbers, zero or more, or empty cells")
