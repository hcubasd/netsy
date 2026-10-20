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


def _required(table, columns):
    missing = [column for column in columns if column not in table.columns]
    if missing:
        raise ValueError(f"missing columns {missing}")
    if table.empty:
        raise ValueError("must have at least one row")


def _filled(table, columns, what="columns"):
    if columns and table[list(columns)].isna().any().any():
        raise ValueError(f"{what} {list(columns)} must not have empty cells")


def _unique(table, columns, what):
    if (table.duplicated(list(columns)).any() if columns else len(table) > 1):
        raise ValueError(f"each {what} may appear only once")


def _any_numbers(table, columns):
    """`table` with `columns` converted to numbers of any sign, every one present."""
    table = table.copy()
    for column in columns:
        values = pd.to_numeric(table[column], errors="coerce")
        if values.isna().any():
            raise ValueError(f"'{column}' must hold numbers in every row")
        table[column] = values
    return table


def _positive(table, columns):
    table = _numbers(table, columns)
    for column in columns:
        if (table[column] <= 0).any():
            raise ValueError(f"'{column}' must hold numbers above 0 in every row")
    return table


def _points(table):
    if table.crs is None:
        raise ValueError("missing CRS")
    if table.geometry.isna().any() or table.geometry.is_empty.any():
        raise ValueError("every row needs a geometry")
    if not table.geometry.geom_type.eq("Point").all():
        raise ValueError("geometries must be points")


def check_agents(agents):
    """`agents.gpkg` with its sizes as numbers: a unique `agent_id`, the
    agent's `zone_id` and other stratum columns, a `size` of zero or more and
    a point geometry.
    """
    _required(agents, ("agent_id", "zone_id", "size"))
    if agents["agent_id"].isna().any() or agents["agent_id"].duplicated().any():
        raise ValueError("'agent_id' values must be present and unique")
    _filled(agents, [column for column in agents.columns if column not in ("size", "geometry")], "stratum columns")
    _points(agents)
    return _numbers(agents, ("size",))


def check_facilities(facilities):
    """Raise ValueError unless every facility has a unique `facility_id`, a
    `facility_type`, the `zone_id` it lies in and a point geometry.
    """
    _required(facilities, ("facility_id", "facility_type", "zone_id"))
    if facilities["facility_id"].isna().any() or facilities["facility_id"].duplicated().any():
        raise ValueError("'facility_id' values must be present and unique")
    _filled(facilities, ("facility_type", "zone_id"))
    _points(facilities)


def check_rates(table):
    """`production_rates.csv` or `consumption_rates.csv` with its rates as
    numbers: key columns and a `rate` of zero or more, one row per key.
    """
    _required(table, ("rate",))
    keys = [column for column in table.columns if column != "rate"]
    if not keys:
        raise ValueError("needs at least one key column, such as 'resource'")
    _filled(table, keys, "key columns")
    _unique(table, keys, "key")
    return _numbers(table, ("rate",))


# The columns of shipment_totals.csv that are not shipment strata.
SHIPMENT_TOTAL_FIELDS = (
    "origin_region", "destination_region", "origin_zone_id", "destination_zone_id", "flow_type", "quantity",
)


def check_shipment_totals(table):
    """`shipment_totals.csv` with its quantities as numbers: one row per
    origin region, destination region, optional pinned zones, flow type and
    shipment stratum (`resource` and any other columns).
    """
    _required(table, ("origin_region", "destination_region", "flow_type", "resource", "quantity"))
    strata = [column for column in table.columns if column not in SHIPMENT_TOTAL_FIELDS]
    _filled(table, ["origin_region", "destination_region", "flow_type"] + strata)
    _unique(table, [column for column in table.columns if column != "quantity"], "region pair, flow type and stratum")
    return _numbers(table, ("quantity",))


def check_flow_types(table):
    """`flow_types.csv` with `distinct` as booleans: per `flow_type`, the
    kind of its `origin` and `destination` (`agent`, `zone`, or a facility
    type), which end, if any, is weighted by distance `decay`, and optional
    facility weight columns, a facility column both ends must share
    (`same`) and whether the ends must differ (`distinct`).
    """
    _required(table, ("flow_type", "origin", "destination"))
    _filled(table, ("flow_type", "origin", "destination"))
    _unique(table, ("flow_type",), "flow type")
    table = table.copy()
    for column in ("decay", "origin_weight", "destination_weight", "same", "distinct"):
        if column not in table.columns:
            table[column] = None
    if not table["decay"].dropna().isin(["origin", "destination"]).all():
        raise ValueError("'decay' must be 'origin', 'destination' or empty")
    distinct = table["distinct"].fillna("false").astype(str).str.lower()
    if not distinct.isin(["true", "false"]).all():
        raise ValueError("'distinct' must be 'true', 'false' or empty")
    table["distinct"] = distinct.eq("true")
    return table


def check_distance_decay(table):
    """`distance_decay.csv` with its values as numbers: per key (any shipment
    strata, or none), the decay's `alpha` and `beta` and the sourcing cost
    per hour and per kilometre.
    """
    values = ("alpha", "beta", "cost_per_hour", "cost_per_km")
    _required(table, values)
    keys = [column for column in table.columns if column not in values]
    _filled(table, keys, "key columns")
    _unique(table, keys, "key")
    return _numbers(_any_numbers(table, ("alpha", "beta")), ("cost_per_hour", "cost_per_km"))


def check_shipment_sizes(table):
    """`shipment_sizes.csv` with its quantities as numbers: a unique
    `size_class` and the `quantity` a shipment of that class carries.
    """
    _required(table, ("size_class", "quantity"))
    _filled(table, ("size_class",))
    _unique(table, ("size_class",), "size class")
    return _positive(table, ("quantity",))


def check_shipment_vehicles(table):
    """`shipment_vehicles.csv` with its values as numbers: a unique
    `vehicle`, its `capacity`, and its cost per hour and per kilometre.
    """
    _required(table, ("vehicle", "capacity", "cost_per_hour", "cost_per_km"))
    _filled(table, ("vehicle",))
    _unique(table, ("vehicle",), "vehicle")
    return _numbers(_positive(table, ("capacity",)), ("cost_per_hour", "cost_per_km"))


def check_choice(table, alternative):
    """A choice-coefficient table (`vehicle_choice.csv` keyed by `vehicle`,
    `delivery_choice.csv` by `window`) with its values as numbers: per key
    (any shipment strata, or none), alternative (empty for every
    alternative) and `term`, a `value`.
    """
    _required(table, ("term", "value"))
    table = table.copy()
    if alternative not in table.columns:
        table[alternative] = None
    keys = [column for column in table.columns if column not in (alternative, "term", "value")]
    _filled(table, keys + ["term"])
    _unique(table, keys + [alternative, "term"], "key, alternative and term")
    return _any_numbers(table, ("value",))


def check_delivery_windows(table):
    """`delivery_windows.csv` with its bounds as numbers: per key (any
    shipment strata, or none), each `window` and its `start` and `end`.
    """
    _required(table, ("window", "start", "end"))
    keys = [column for column in table.columns if column not in ("window", "start", "end")]
    _filled(table, keys + ["window"])
    _unique(table, keys + ["window"], "key and window")
    table = _any_numbers(table, ("start", "end"))
    if (table["end"] <= table["start"]).any():
        raise ValueError("every window must end after it starts")
    return table
