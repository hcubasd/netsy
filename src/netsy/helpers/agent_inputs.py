import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

from netsy.helpers.validate import DISTRIBUTION_KEYS


@dataclass(frozen=True)
class Resource:
    """What one resource contributes to a stratum: its aggregate supply and
    demand, and the capacity and need distributions as ascending levels with
    their cumulative probabilities.
    """

    supply: int
    demand: int
    capacity_levels: np.ndarray
    capacity_cumulative: np.ndarray
    need_levels: np.ndarray
    need_cumulative: np.ndarray


@dataclass(frozen=True)
class Stratum:
    dims: dict
    polygon: object
    resources: dict


@dataclass(frozen=True)
class AgentInputs:
    dims: list
    resources: list
    strata: list


def _zone_key(value):
    # A zone id compares as text, whether it came from a CSV or a geopackage.
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def _with_amounts(table, dims, name):
    """A copy of a supply or demand table whose non-stratum columns are
    numeric, plus the names of those resource columns. A non-numeric column
    is most likely a stratum that capacities and needs do not have.
    """
    table = table.copy()
    resources = [c for c in table.columns if c not in dims]
    for column in resources:
        try:
            table[column] = pd.to_numeric(table[column])
        except (ValueError, TypeError):
            raise ValueError(
                f"{name}: column '{column}' is not numeric; if it is a stratum, "
                "capacities and needs must have it too"
            ) from None
        values = table[column].dropna()
        if (values < 0).any() or (values % 1 != 0).any():
            raise ValueError(f"{name}: column '{column}' must hold whole numbers, zero or more")
    if table.duplicated(dims).any():
        raise ValueError(f"{name}: each stratum may appear only once")
    return table, resources


def _distributions(table, dims):
    distributions = {}
    for key, group in table.groupby(dims + ["resource"], sort=False):
        group = group.sort_values("resource_level")
        levels = group["resource_level"].to_numpy(dtype=np.int64)
        distributions[key] = (levels, np.cumsum(group["probability"].to_numpy(dtype=float)))
    return distributions


def combine_agent_inputs(supply, demand, capacities, needs, zones):
    """Match the five inputs into the strata agents are drawn from.

    All four tables must have the same stratum columns, `zone_id` among
    them. A stratum is used only if it is in supply and demand, its zone is
    in `zones`, and at least one resource is usable in it. A resource is
    usable in a stratum only if it has a supply and a demand there and both a
    capacity and a need distribution: an agent needs a valid draw for every
    resource at once, so one missing from any of the four is left out.
    Strata that yield nothing are reported in a warning.
    """
    capacity_dims = [c for c in capacities.columns if c not in DISTRIBUTION_KEYS]
    if set(capacity_dims) != {c for c in needs.columns if c not in DISTRIBUTION_KEYS}:
        raise ValueError("capacities and needs must have the same stratum columns")
    if "zone_id" not in capacity_dims:
        raise ValueError("capacities and needs must have a 'zone_id' column")
    for name, table in (("supply", supply), ("demand", demand)):
        missing = sorted(set(capacity_dims) - set(table.columns))
        if missing:
            raise ValueError(f"{name}: missing stratum columns {missing}")

    dims = [c for c in supply.columns if c in capacity_dims]
    supply, supply_resources = _with_amounts(supply, dims, "supply")
    demand, demand_resources = _with_amounts(demand, dims, "demand")
    resources = [r for r in supply_resources if r in demand_resources]

    capacity = _distributions(capacities, dims)
    need = _distributions(needs, dims)
    zone_of = {_zone_key(z): (z, geometry) for z, geometry in zip(zones["zone_id"].tolist(), zones.geometry)}
    demand_of = {tuple(row[d] for d in dims): row for row in demand.to_dict("records")}

    strata, skipped = [], 0
    for row in supply.to_dict("records"):
        key = tuple(row[d] for d in dims)
        zone = zone_of.get(_zone_key(row["zone_id"]))
        paired = demand_of.get(key)
        usable = {}
        if zone is not None and paired is not None:
            for resource in resources:
                if pd.isna(row[resource]) or pd.isna(paired[resource]):
                    continue
                if (key + (resource,)) not in capacity or (key + (resource,)) not in need:
                    continue
                usable[resource] = Resource(
                    int(row[resource]), int(paired[resource]),
                    *capacity[key + (resource,)], *need[key + (resource,)],
                )
        if not usable:
            skipped += 1
            continue
        values = dict(zip(dims, key))
        values["zone_id"] = zone[0]
        strata.append(Stratum(values, zone[1], usable))

    if skipped:
        warnings.warn(
            f"{skipped} of {len(supply)} strata yield no agents: their zone is not in the zones file, "
            "or no resource is defined for them in all of supply, demand, capacities and needs",
            stacklevel=2,
        )
    return AgentInputs(dims, resources, strata)
