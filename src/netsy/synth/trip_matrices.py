"""Trip matrices between zones by gravity, as MASS-GT's service module
(SERVICE) derives its van trips, generalized to any segments and zone
attributes.

Per segment, each zone produces, and attracts as many, trips as the sum of
its attributes times the segment's rates. A gravity prior, 1 / (1 +
exp(alpha) cost^beta) times the two zones' productions, with cost the
segment's cost per hour and per kilometre over the skims, is balanced to
them with FRATAR (MASS-GT's 25 iterations and 0.005 tolerance). Trips
between two external zones are then dropped, and trips are kept to a
thousandth.
"""

import numpy as np
import pandas as pd

from netsy.helpers.fratar import fratar
from netsy.synth.agents import _zone_key
from netsy.synth.shipments import _intrazonal

TOLERANCE, MAX_ITERATIONS = 0.005, 25


def trip_matrices(zones, skims, attributes, rates, decay):
    """`{segment: trips}`, a zone-by-zone matrix per segment in the order of
    the skims' zones. Raises ValueError if the tables do not fit together.
    """
    zone_ids, time, distance = skims
    skim_index = {zone: index for index, zone in enumerate(zone_ids)}
    time, distance = _intrazonal(np.array(time, dtype=np.float32)), _intrazonal(np.array(distance, dtype=np.float32))
    keys = attributes["zone_id"].map(_zone_key)
    unknown = sorted(set(keys) - set(skim_index))
    if unknown:
        raise ValueError(f"trip_attributes.csv: zones {unknown[:5]} are not in the skims")
    missing = sorted(set(rates["attribute"]) - set(attributes.columns))
    if missing:
        raise ValueError(f"trip_rates.csv: attributes {missing} are not columns of trip_attributes.csv")
    external = np.zeros(len(zone_ids), dtype=bool)
    if "external" in zones.columns:
        flags = pd.to_numeric(zones["external"], errors="coerce").fillna(0).to_numpy() > 0
        indices = zones["zone_id"].map(_zone_key).map(skim_index)
        external[indices[indices.notna()].astype(int).to_numpy()] = flags[indices.notna().to_numpy()]
    decay = decay.set_index(decay["segment"].map(_zone_key))
    result = {}
    for segment, group in rates.groupby(rates["segment"].map(_zone_key), sort=True):
        if segment not in decay.index:
            raise ValueError(f"trip_decay.csv: no parameters for segment {segment!r}")
        values = attributes[group["attribute"].tolist()].apply(pd.to_numeric, errors="coerce")
        if values.isna().any().any():
            raise ValueError("trip_attributes.csv: attributes must hold numbers in every row")
        productions = np.zeros(len(zone_ids))
        np.add.at(productions, keys.map(skim_index).to_numpy(), values.to_numpy(float) @ pd.to_numeric(group["rate"]).to_numpy(float))
        row = decay.loc[segment]
        alpha, beta, per_hour, per_km = (float(row[name]) for name in ("alpha", "beta", "cost_per_hour", "cost_per_km"))
        cost = per_hour * time.astype(np.float64) + per_km * distance
        with np.errstate(over="ignore"):
            trips = 100 / (1 + np.exp(alpha) * cost ** beta)
        del cost
        trips *= productions[None, :]
        trips *= productions[:, None]
        trips, _ = fratar(trips, productions, productions, TOLERANCE, MAX_ITERATIONS)
        trips[np.ix_(external, external)] = 0
        # To a thousandth of a trip, as MASS-GT stores them.
        result[segment] = np.round(trips, 3).astype(np.float32)
    return result
