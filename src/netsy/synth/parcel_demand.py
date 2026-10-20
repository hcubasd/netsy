"""Parcel demand per zone, as MASS-GT's parcel demand module (PARCEL_DMND)
derives it, generalized to any zone attributes, population strata and
operators.

Business parcels are linear in zone attributes, such as jobs. Consumer
parcels follow an ordered logit per person: each population cell's utility
is the sum of the terms that match it, and the probability of ordering at
most a level's number of parcels in a period is 1 / (1 + exp(utility -
threshold)). A cell orders its persons times its expected parcels per
period, divided by the period's length, and the consumer total is then
scaled to a number of parcels per person. Each zone's parcels are split
over operators by market share, rounded per operator, and sent from the
operator's depot nearest the zone in travel time.
"""

import numpy as np
import pandas as pd

from netsy.synth.agents import _zone_key
from netsy.synth.shipments import _intrazonal

SETTINGS = {"depot_type": "parcel_depot", "operator_column": "operator", "period": 1.0, "per_person": None}


def _settings(table):
    values = dict(SETTINGS)
    for row in table.to_dict("records"):
        name = row["setting"]
        if name not in values:
            raise ValueError(f"parcel_settings.csv: unknown setting {name!r}; settings are {sorted(SETTINGS)}")
        values[name] = row["value"]
    for name in ("period", "per_person"):
        if values[name] is not None:
            number = pd.to_numeric(values[name], errors="coerce")
            if pd.isna(number) or number <= 0:
                raise ValueError(f"parcel_settings.csv: {name!r} must be a number above 0")
            values[name] = float(number)
    return values


def _numbers(table, columns, name):
    values = table[columns].apply(pd.to_numeric, errors="coerce")
    if values.isna().any().any():
        raise ValueError(f"{name}: {columns} must hold numbers in every row")
    return values


def _expected_per_person(population, levels, utility):
    """Each population cell's expected parcels per person in a period."""
    strata = [column for column in population.columns if column not in ("zone_id", "persons")]
    keys = [column for column in utility.columns if column != "value"]
    extra = sorted(set(keys) - set(strata))
    if extra:
        raise ValueError(f"order_utility.csv: columns {extra} are not population strata")
    cells = population[keys].map(_zone_key) if keys else pd.DataFrame(index=population.index)
    total = np.zeros(len(population))
    for row in utility.to_dict("records"):
        match = np.ones(len(population), dtype=bool)
        for key in keys:
            if not pd.isna(row[key]):
                match &= (cells[key] == _zone_key(row[key])).to_numpy()
        total += match * float(row["value"])
    thresholds = pd.to_numeric(levels["threshold"], errors="coerce").to_numpy(dtype=float)
    quantities = pd.to_numeric(levels["quantity"], errors="coerce").to_numpy(dtype=float)
    if np.isnan(quantities).any() or np.isnan(thresholds[:-1]).any():
        raise ValueError("order_levels.csv: every level needs a 'quantity', and every level but the last a 'threshold'")
    cumulative = np.ones((len(population), len(levels)))
    cumulative[:, :-1] = 1 / (1 + np.exp(total[:, None] - thresholds[None, :-1]))
    probabilities = np.diff(cumulative, axis=1, prepend=0.0)
    return probabilities @ quantities


def parcel_demand(zones, facilities, skims, attributes_table, rates, population, levels, utility, shares, settings):
    """One row per destination zone, operator and depot: the depot's zone
    and the number of `parcels`. Raises ValueError if the tables do not fit
    together.
    """
    values = _settings(settings)
    zone_ids, time, _ = skims
    time = _intrazonal(np.array(time, dtype=np.float32))
    skim_index = {zone: index for index, zone in enumerate(zone_ids)}
    known = set(zones["zone_id"].map(_zone_key))

    def zone_keys(table, name):
        keys = table["zone_id"].map(_zone_key)
        unknown = sorted(set(keys) - known)
        if unknown:
            raise ValueError(f"{name}: zones {unknown[:5]} are not in zones.gpkg")
        return keys

    # Business parcels: linear in the zone attributes.
    attribute_zones = zone_keys(attributes_table, "parcel_attributes.csv")
    unknown = sorted(set(rates["attribute"]) - set(attributes_table.columns))
    if unknown:
        raise ValueError(f"parcel_rates.csv: attributes {unknown} are not columns of parcel_attributes.csv")
    attributes = _numbers(attributes_table, list(rates["attribute"]), "parcel_attributes.csv")
    business = pd.Series(
        attributes.to_numpy(dtype=float) @ pd.to_numeric(rates["rate"]).to_numpy(dtype=float), index=attribute_zones,
    ).groupby(level=0).sum()

    # Consumer parcels: an ordered logit per population cell.
    persons = _numbers(population, ["persons"], "population.csv")["persons"].to_numpy(dtype=float)
    per_person = _expected_per_person(population, levels, utility)
    consumer = pd.Series(persons * per_person / values["period"], index=zone_keys(population, "population.csv"))
    consumer = consumer.groupby(level=0).sum()
    if values["per_person"] is not None and consumer.sum() > 0:
        consumer *= values["per_person"] * persons.sum() / consumer.sum()
    total = business.add(consumer, fill_value=0.0)

    # Depots: each operator's depots, by the travel time from them to a zone.
    column = values["operator_column"]
    if column not in facilities.columns:
        raise ValueError(f"facilities.gpkg: missing column {column!r}")
    depots = facilities[facilities["facility_type"].map(_zone_key) == values["depot_type"]]
    if depots.empty:
        raise ValueError(f"facilities.gpkg: no facility has type {values['depot_type']!r}")
    share = dict(zip(shares["operator"].map(_zone_key), pd.to_numeric(shares["share"], errors="coerce")))
    if any(pd.isna(value) or value < 0 for value in share.values()):
        raise ValueError("operator_shares.csv: 'share' must hold numbers of at least 0")
    rows = []
    for operator, group in depots.groupby(depots[column].map(_zone_key), sort=True):
        if operator not in share:
            raise ValueError(f"operator_shares.csv: no share for operator {operator!r}")
        depot_ids = group["facility_id"].tolist()
        depot_zones = group["zone_id"].map(_zone_key).tolist()
        missing = sorted(set(depot_zones) - set(skim_index))
        if missing:
            raise ValueError(f"facilities.gpkg: zones {missing} of {operator!r} depots are not in the skims")
        depot_index = np.array([skim_index[zone] for zone in depot_zones])
        for zone, parcels in total.items():
            count = int(np.round(share[operator] * parcels))
            if count <= 0:
                continue
            nearest = int(np.argmin(time[depot_index, skim_index[zone]]))
            rows.append((zone, operator, depot_ids[nearest], depot_zones[nearest], count))
    original = dict(zip(zones["zone_id"].map(_zone_key), zones["zone_id"]))
    table = pd.DataFrame(rows, columns=["destination_zone_id", "operator", "facility_id", "origin_zone_id", "parcels"])
    table["destination_zone_id"] = table["destination_zone_id"].map(original)
    table["origin_zone_id"] = table["origin_zone_id"].map(original)
    return table.sort_values(["destination_zone_id", "operator"], kind="stable").reset_index(drop=True)
