"""Balance resource-specific origin-destination flows with IPF/Furness."""

from __future__ import annotations

import numpy as np
import pandas as pd


_MARGINAL_COLUMNS = {"resource", "location_id", "quantity"}
_PRIOR_COLUMNS = {"resource", "origin_location_id", "destination_location_id", "weight"}


def _marginals(table, name):
    missing = _MARGINAL_COLUMNS - set(table.columns)
    if missing:
        raise ValueError(f"{name}: missing columns {sorted(missing)}")
    values = pd.to_numeric(table["quantity"], errors="coerce")
    if values.isna().any() or (values < 0).any():
        raise ValueError(f"{name}: 'quantity' must contain non-negative numbers")
    if table[["resource", "location_id"]].isna().any().any():
        raise ValueError(f"{name}: resource and location_id values must be present")
    if table.duplicated(["resource", "location_id"]).any():
        raise ValueError(f"{name}: each resource and location_id pair must be unique")
    return table.assign(quantity=values.astype(float))


def _prior(table):
    missing = _PRIOR_COLUMNS - set(table.columns)
    if missing:
        raise ValueError(f"od prior: missing columns {sorted(missing)}")
    values = pd.to_numeric(table["weight"], errors="coerce")
    if values.isna().any() or (values < 0).any():
        raise ValueError("od prior: 'weight' must contain non-negative numbers")
    keys = ["resource", "origin_location_id", "destination_location_id"]
    if table[keys].isna().any().any():
        raise ValueError("od prior: resource and location identifiers must be present")
    if table.duplicated(keys).any():
        raise ValueError("od prior: each resource and origin/destination pair must be unique")
    return table.assign(weight=values.astype(float))


def od_flows(productions, attractions, prior, *, tolerance=1e-8, max_iterations=1_000):
    """Balance positive OD prior weights to production and attraction totals.

    This is doubly constrained iterative proportional fitting (also known as
    Furness/FRATAR). The prior can be gravity, impedance, observed partial
    flow, or another explicitly documented support matrix. It never creates
    unsupported OD pairs, so an unserviceable marginal fails clearly.
    """
    productions = _marginals(productions, "productions")
    attractions = _marginals(attractions, "attractions")
    prior = _prior(prior)
    if tolerance <= 0 or max_iterations < 1:
        raise ValueError("tolerance must be positive and max_iterations must be at least one")
    rows = []
    resources = sorted(set(productions["resource"]) | set(attractions["resource"]))
    for resource in resources:
        production = productions.loc[productions["resource"] == resource, ["location_id", "quantity"]]
        attraction = attractions.loc[attractions["resource"] == resource, ["location_id", "quantity"]]
        if production.empty or attraction.empty:
            raise ValueError(f"resource {resource!r}: both production and attraction marginals are required")
        production = production.set_index("location_id")["quantity"]
        attraction = attraction.set_index("location_id")["quantity"]
        total_production = production.sum()
        total_attraction = attraction.sum()
        if not np.isclose(total_production, total_attraction, rtol=tolerance, atol=tolerance):
            raise ValueError(
                f"resource {resource!r}: production total {total_production:g} does not equal attraction total {total_attraction:g}"
            )
        weights = prior.loc[prior["resource"] == resource].copy()
        if weights.empty and total_production > 0:
            raise ValueError(f"resource {resource!r}: no OD prior rows")
        origins = production.index.tolist()
        destinations = attraction.index.tolist()
        weight_matrix = (
            weights.pivot(
                index="origin_location_id",
                columns="destination_location_id",
                values="weight",
            )
            .reindex(index=origins, columns=destinations, fill_value=0.0)
            .fillna(0.0)
            .to_numpy(dtype=float)
        )
        if total_production == 0:
            continue
        if (weight_matrix[production.to_numpy() > 0].sum(axis=1) == 0).any():
            raise ValueError(f"resource {resource!r}: a producing location has no supported destination")
        if (weight_matrix[:, attraction.to_numpy() > 0].sum(axis=0) == 0).any():
            raise ValueError(f"resource {resource!r}: an attracting location has no supported origin")
        flows = weight_matrix.copy()
        production_values = production.to_numpy()
        attraction_values = attraction.to_numpy()
        for _ in range(max_iterations):
            row_totals = flows.sum(axis=1)
            flows *= np.divide(production_values, row_totals, out=np.zeros_like(row_totals), where=row_totals > 0)[:, None]
            column_totals = flows.sum(axis=0)
            flows *= np.divide(attraction_values, column_totals, out=np.zeros_like(column_totals), where=column_totals > 0)[None, :]
            error = max(
                np.max(np.abs(flows.sum(axis=1) - production_values)),
                np.max(np.abs(flows.sum(axis=0) - attraction_values)),
            )
            if error <= tolerance:
                break
        else:
            raise ValueError(f"resource {resource!r}: IPF did not converge in {max_iterations} iterations")
        for origin_index, origin in enumerate(origins):
            for destination_index, destination in enumerate(destinations):
                quantity = flows[origin_index, destination_index]
                if quantity > 0:
                    rows.append(
                        {
                            "resource": resource,
                            "origin_location_id": origin,
                            "destination_location_id": destination,
                            "quantity": quantity,
                        }
                    )
    return pd.DataFrame(rows, columns=["resource", "origin_location_id", "destination_location_id", "quantity"])
