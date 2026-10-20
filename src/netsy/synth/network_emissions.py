"""Emissions of the network loads, by MASS-GT's emission factors or by
COPERT V.

With MASS-GT's factors (the port of its traffic assignment's emissions),
each vehicle and road type has an empty and a full factor in grams per
kilometre; a load's factor lies between them by its utilization, and its
grams are that factor times the link's length times its trips. A road type
without factors emits nothing.

With COPERT V (a contribution to the port), a load's hot-exhaust factor
follows COPERT V's speed function for its vehicle's COPERT type, at the
link's grade and the load's payload, each snapped to COPERT's bins, and
non-exhaust emissions are flat factors per kilometre, independent of speed.
A speed outside a coefficient row's `min_speed` and `max_speed` counts as the
nearest of them.
"""

import bisect

import numpy as np
import pandas as pd

from netsy.synth.agents import _zone_key

GRADIENT_BINS = (-6, -4, -2, 0, 2, 4, 6)
PAYLOAD_BINS = (0, 50, 100)
METHODS = ("factors", "copert")
KEYS = ["link_id", "time_interval", "vehicle", "segment"]


def _snap(value, bins):
    index = bisect.bisect_left(bins, value)
    if index == 0:
        return bins[0]
    if index == len(bins):
        return bins[-1]
    before, after = bins[index - 1], bins[index]
    return before if abs(value - before) <= abs(value - after) else after


def _hot_emission_factor(coefficients, velocity):
    """COPERT V's hot-exhaust factor in grams per kilometre, for arrays of
    coefficients and speeds.
    """
    velocity = np.asarray(velocity, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        denominator = coefficients["epsilon"] * velocity ** 2 + coefficients["zeta"] * velocity + coefficients["eta"]
        numerator = (
            coefficients["alpha"] * velocity ** 2 + coefficients["beta"] * velocity + coefficients["gamma"]
            + coefficients["delta"] / velocity
        )
        factor = numerator / denominator * (1 - coefficients["rf"])
    return np.where((velocity > 0) & (denominator != 0), np.maximum(factor, 0.0), np.nan)


def _links(network, loads):
    links = pd.DataFrame({
        "link_id": network["link_id"].map(_zone_key),
        "length": pd.to_numeric(network["length"], errors="coerce"),
        "road_type": network["road_type"].map(_zone_key) if "road_type" in network.columns else "",
        "grade": pd.to_numeric(network["grade"], errors="coerce") if "grade" in network.columns else 0.0,
    })
    if links["length"].isna().any() or links["grade"].isna().any():
        raise ValueError("network.gpkg: 'length' and 'grade' must hold numbers in every row")
    table = loads.assign(link_id=loads["link_id"].map(_zone_key), vehicle=loads["vehicle"].map(_zone_key))
    table = table.merge(links, on="link_id", how="left")
    if table["length"].isna().any():
        raise ValueError("network_loads.parquet: every 'link_id' must be a link of network.gpkg")
    for column in ("trips", "utilization", "speed"):
        table[column] = pd.to_numeric(table[column], errors="coerce")
    return table


def emissions_by_factors(loads, network, factors):
    """Grams per load row and pollutant by MASS-GT's empty and full factors."""
    table = _links(network, loads)
    factors = factors.assign(
        vehicle=factors["vehicle"].map(_zone_key), road_type=factors["road_type"].map(_zone_key),
        empty=pd.to_numeric(factors["empty"], errors="coerce"), full=pd.to_numeric(factors["full"], errors="coerce"),
    )
    if factors[["empty", "full"]].isna().any().any():
        raise ValueError("emission_factors.csv: 'empty' and 'full' must hold numbers in every row")
    result = table[KEYS].copy()
    for pollutant, group in factors.groupby("pollutant", sort=True):
        rates = table[["vehicle", "road_type"]].merge(
            group[["vehicle", "road_type", "empty", "full"]], on=["vehicle", "road_type"], how="left",
        )
        factor = rates["empty"].to_numpy() + table["utilization"].to_numpy() * (rates["full"] - rates["empty"]).to_numpy()
        result[pollutant] = np.nan_to_num(factor) * table["length"].to_numpy() * table["trips"].to_numpy()
    return result


def emissions_by_copert(loads, network, copert_vehicles, coefficients, non_exhaust):
    """Grams per load row and pollutant by COPERT V: `<pollutant>` for hot
    exhaust and `<pollutant>_non_exhaust` for the flat factors.
    """
    table = _links(network, loads)
    types = dict(zip(copert_vehicles["vehicle"].map(_zone_key), copert_vehicles["vehicle_type"].map(_zone_key)))
    table["vehicle_type"] = table["vehicle"].map(types)
    table["gradient_bin"] = [_snap(value, GRADIENT_BINS) for value in table["grade"]]
    table["payload_bin"] = [_snap(value * 100, PAYLOAD_BINS) for value in table["utilization"].fillna(0)]
    distance = table["length"].to_numpy() * table["trips"].to_numpy()
    coefficients = coefficients.assign(
        vehicle_type=coefficients["vehicle_type"].map(_zone_key),
        gradient_bin=pd.to_numeric(coefficients["gradient_bin"]), payload_bin=pd.to_numeric(coefficients["payload_bin"]),
    )
    names = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "rf"]
    coefficients[names] = coefficients[names].apply(pd.to_numeric, errors="coerce")
    if coefficients[names].isna().any().any():
        raise ValueError("copert_v_coefficients.csv: 'alpha' to 'eta' and 'rf' must hold numbers in every row")
    result = table[KEYS].copy()
    keys = ["vehicle_type", "gradient_bin", "payload_bin"]
    # COPERT's speeds of validity, if given: a speed outside them counts as
    # the nearest.
    bounds = [column for column in ("min_speed", "max_speed") if column in coefficients.columns]
    coefficients[bounds] = coefficients[bounds].apply(pd.to_numeric, errors="coerce")
    for pollutant, group in coefficients.groupby("pollutant", sort=True):
        rows = table[keys].merge(group[keys + names + bounds], on=keys, how="left")
        speed = table["speed"].to_numpy(float)
        if bounds:
            speed = np.clip(speed, rows.get("min_speed", pd.Series(-np.inf, index=rows.index)).fillna(-np.inf).to_numpy(),
                            rows.get("max_speed", pd.Series(np.inf, index=rows.index)).fillna(np.inf).to_numpy())
        factor = _hot_emission_factor({name: rows[name].to_numpy() for name in names}, speed)
        result[pollutant] = np.nan_to_num(factor) * distance
    flat = non_exhaust.assign(
        vehicle_type=non_exhaust["vehicle_type"].map(_zone_key),
        emission_factor=pd.to_numeric(non_exhaust["emission_factor"], errors="coerce"),
    )
    for pollutant, group in flat.groupby("pollutant", sort=True):
        factor = table["vehicle_type"].map(dict(zip(group["vehicle_type"], group["emission_factor"]))).fillna(0.0)
        result[f"{pollutant}_non_exhaust"] = factor.to_numpy() * distance
    return result
