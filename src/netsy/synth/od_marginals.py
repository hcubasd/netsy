"""Production and attraction totals per location from linear regressions on
location attributes, as MASS-GT's spatial interaction freight module (SIF)
derives them.
"""

import numpy as np
import pandas as pd


def od_marginals(attributes, coefficients, prior):
    """`(productions, attractions)` for the locations of `attributes`: per
    resource, the sum over attributes of each coefficient times the
    location's attribute value. A location whose attributes are all empty,
    such as a foreign country, keeps its prior row total as its production
    and its column total as its attraction. Raises ValueError if the tables
    do not fit together.
    """
    if "location_id" not in attributes.columns:
        raise ValueError("location_attributes.csv: missing 'location_id' column")
    missing = [column for column in ("resource", "attribute", "production", "attraction") if column not in coefficients.columns]
    if missing:
        raise ValueError(f"marginal_coefficients.csv: missing columns {missing}")
    names = [column for column in attributes.columns if column != "location_id"]
    unknown = sorted(set(coefficients["attribute"]) - set(names))
    if unknown:
        raise ValueError(f"marginal_coefficients.csv: attributes {unknown} are not columns of location_attributes.csv")
    if attributes["location_id"].duplicated().any():
        raise ValueError("location_attributes.csv: each location may appear only once")
    values = attributes[names].apply(pd.to_numeric, errors="coerce")
    blank = attributes[names].isna().all(axis=1).to_numpy()
    if values[~blank].isna().any().any():
        raise ValueError("location_attributes.csv: attributes must hold numbers, or all be empty to keep the prior totals")
    for column in ("production", "attraction"):
        if pd.to_numeric(coefficients[column], errors="coerce").isna().any():
            raise ValueError(f"marginal_coefficients.csv: '{column}' must hold numbers in every row")
    locations = attributes["location_id"].astype(str).to_numpy()
    prior = prior.assign(weight=pd.to_numeric(prior["weight"], errors="coerce"))
    resources = sorted(set(coefficients["resource"].astype(str)) | set(prior["resource"].astype(str)))
    tables = {"production": [], "attraction": []}
    for resource in resources:
        rows = coefficients[coefficients["resource"].astype(str) == resource]
        weights = prior[prior["resource"].astype(str) == resource]
        for side, end in (("production", "origin_location_id"), ("attraction", "destination_location_id")):
            matrix = values[rows["attribute"].tolist()].fillna(0).to_numpy(dtype=float)
            totals = matrix @ pd.to_numeric(rows[side]).to_numpy(dtype=float) if len(rows) else np.zeros(len(locations))
            kept = weights.groupby(weights[end].astype(str))["weight"].sum()
            totals = np.where(blank, [kept.get(location, 0.0) for location in locations], totals)
            tables[side] += [(resource, location, total) for location, total in zip(locations, totals)]
    return tuple(pd.DataFrame(tables[side], columns=["resource", "location_id", "quantity"]) for side in ("production", "attraction"))
