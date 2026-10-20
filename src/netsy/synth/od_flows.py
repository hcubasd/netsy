"""Balance resource-specific origin-destination flows with FRATAR (IPF/Furness)."""

from __future__ import annotations

import warnings

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


def od_flows(productions, attractions, prior, *, tolerance=0.005, max_iterations=50):
    """Balance positive OD prior weights to production and attraction totals
    with FRATAR, as MASS-GT's spatial interaction freight module (SIF) does.

    Each iteration scales every destination's column to its attraction,
    then every origin's row to its production, so the result always matches
    the productions; it matches the attractions as closely as the prior
    allows, and exactly when the totals agree and it converges. Iterations
    stop once the largest scaling factor of either pass is within
    `tolerance` of one, once that measure stops changing, or after
    `max_iterations`. The prior can be gravity, impedance, observed partial
    flow, or another explicitly documented support matrix. It never creates
    unsupported OD pairs: a marginal without support stays unmet, with a
    warning.
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
        weights = prior.loc[prior["resource"] == resource].copy()
        if weights.empty and production.sum() > 0:
            raise ValueError(f"resource {resource!r}: no OD prior rows")
        if production.sum() == 0:
            continue
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
        # A location the prior gives no counterpart keeps no flow, as in
        # MASS-GT; it is reported rather than silently scaled away.
        for name, totals, support in (
            ("production", production, weight_matrix.sum(axis=1)), ("attraction", attraction, weight_matrix.sum(axis=0)),
        ):
            unsupported = totals.index[(totals.to_numpy() > 0) & (support == 0)].tolist()
            if unsupported:
                warnings.warn(f"resource {resource!r}: the prior gives no flow to the {name} of {unsupported}; it stays unmet")
        flows = weight_matrix.copy()
        production_values = production.to_numpy()
        attraction_values = attraction.to_numpy()
        previous = None
        for _ in range(max_iterations):
            factors = []
            for axis, targets in ((0, attraction_values), (1, production_values)):
                totals = flows.sum(axis=axis)
                scale = np.divide(targets, totals, out=np.ones_like(totals), where=totals > 0)
                flows *= scale[None, :] if axis == 0 else scale[:, None]
                # The pass's largest factor, as MASS-GT measures convergence.
                used = scale[totals > 0]
                factors.append(used[np.argmax(np.abs(used))] if len(used) else 0.0)
            convergence = round(max(abs(factors[0] - 1), abs(factors[1] - 1)), 5)
            if convergence <= tolerance or convergence == previous:
                break
            previous = convergence
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
