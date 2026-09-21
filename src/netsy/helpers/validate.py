import pandas as pd

EFFECT_KEYS = ("stratum", "stratum_value")
THRESHOLD_COLUMNS = {"resource", "resource_level", "threshold"}
# Column names the combiners write themselves, so a stratum dimension may not
# reuse them.
OUTPUT_KEYS = ("resource", "resource_level", "probability")


def check_effects(effects):
    """Raise ValueError unless `effects` is a usable effects table: a
    `stratum` / `stratum_value` pair of columns identifying each effect, plus
    one numeric column per resource. `zone_id` must be one of the strata,
    every (stratum, stratum_value) pair must be unique, and no stratum may
    share a name with a resource or with a column the combiners write.
    Empty resource cells are allowed: they mean the stratum value does not
    participate in that resource.
    """
    for column in EFFECT_KEYS:
        if column not in effects.columns:
            raise ValueError(f"missing '{column}' column")
    resources = [c for c in effects.columns if c not in EFFECT_KEYS]
    if not resources:
        raise ValueError("must have at least one resource column")
    if effects[list(EFFECT_KEYS)].isna().any().any():
        raise ValueError("'stratum' and 'stratum_value' must not have empty cells")
    strata = set(effects["stratum"])
    if "zone_id" not in strata:
        raise ValueError("'zone_id' must be present among the strata")
    clashes = strata & (set(resources) | set(OUTPUT_KEYS))
    if clashes:
        raise ValueError(f"stratum names clash with resource or output columns: {sorted(clashes)}")
    duplicated = effects.loc[effects.duplicated(list(EFFECT_KEYS)), list(EFFECT_KEYS)]
    if not duplicated.empty:
        pairs = [tuple(pair) for pair in duplicated.to_numpy()]
        raise ValueError(f"duplicate (stratum, stratum_value) pairs: {pairs}")
    for resource in resources:
        if not pd.api.types.is_numeric_dtype(effects[resource]):
            raise ValueError(f"resource column '{resource}' must be numeric")


def check_thresholds(thresholds):
    """Raise ValueError unless `thresholds` is a usable thresholds table:
    exactly `resource`, `resource_level` and `threshold` columns, integer
    levels, and per resource distinct levels whose thresholds are sorted
    ascending with the largest level, and only that one, left empty -- a
    resource with K levels has K - 1 cutpoints.
    """
    if set(thresholds.columns) != THRESHOLD_COLUMNS:
        raise ValueError("must have exactly 'resource', 'resource_level', 'threshold' columns")
    if thresholds.empty:
        raise ValueError("must have at least one row")
    if thresholds["resource"].isna().any():
        raise ValueError("'resource' must not have empty cells")
    if not pd.api.types.is_integer_dtype(thresholds["resource_level"]):
        raise ValueError("'resource_level' must contain integers only")
    if not pd.api.types.is_numeric_dtype(thresholds["threshold"]):
        raise ValueError("'threshold' must be numeric")
    for resource, group in thresholds.groupby("resource", sort=False):
        group = group.sort_values("resource_level")
        if group["resource_level"].duplicated().any():
            raise ValueError(f"resource '{resource}': levels must be distinct")
        cutpoints = group["threshold"]
        if cutpoints.iloc[:-1].isna().any() or not pd.isna(cutpoints.iloc[-1]):
            raise ValueError(f"resource '{resource}': every level but the largest needs a threshold, and the largest must have none")
        if not cutpoints.iloc[:-1].is_monotonic_increasing:
            raise ValueError(f"resource '{resource}': thresholds must be sorted ascending by level")
