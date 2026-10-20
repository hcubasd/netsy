"""Scenario-driven powertrain choices and pollutant/source multipliers."""
import numpy as np
import pandas as pd
from netsy.synth.agents import _zone_key


def tour_combustion(trips, zones, facilities, shares, zone_column, rng):
    if not {"combustion", "share"} <= set(shares):
        raise ValueError("combustion shares require combustion and share columns")
    if zone_column not in zones:
        raise ValueError(f"zones.gpkg: missing combustion zone column {zone_column!r}")
    flags = dict(zip(zones.zone_id.map(_zone_key), pd.to_numeric(zones[zone_column], errors='raise') > 0))
    types = {} if facilities is None else dict(zip(facilities.facility_id.map(_zone_key), facilities.facility_type))
    keys = [c for c in shares if c not in ('combustion', 'share')]
    result = trips.copy()
    chosen = np.full(len(result), 'fuel', dtype=object)
    cache = {}
    for _, positions in result.groupby('tour_id', sort=False).indices.items():
        group = result.iloc[positions]
        first = group.iloc[0].to_dict()
        visited = set(group.origin_zone_id.map(_zone_key)) | set(group.destination_zone_id.map(_zone_key))
        inside = [flags[z] for z in visited]
        first.update(carrier_type=types.get(str(first['carrier']), 'independent'),
                     zone_relation='all' if all(inside) else 'some' if any(inside) else 'none')
        cache_key = tuple(_zone_key(first[key]) for key in keys)
        if cache_key in cache:
            alternatives, weights = cache[cache_key]
            chosen[positions] = rng.choice(alternatives, p=weights)
            continue
        mask = np.ones(len(shares), bool)
        for key in keys:
            if key not in first:
                raise ValueError(f"combustion_shares.csv: unknown choice key {key!r}")
            mask &= shares[key].isna() | (shares[key].map(_zone_key) == _zone_key(first[key]))
        rows = shares.loc[mask]
        if rows.empty:
            raise ValueError(f"combustion_shares.csv: no choice for carrier {first['carrier']!r}, vehicle {first['vehicle']!r}")
        # Exact rules override wildcard rules; equally specific alternatives form one distribution.
        specificity = rows[keys].notna().sum(axis=1)
        rows = rows.loc[specificity == specificity.max()]
        if len(rows[keys].drop_duplicates()) > 1:
            raise ValueError("combustion shares: equally specific wildcard rules overlap")
        weights = pd.to_numeric(rows['share'], errors='raise').to_numpy(float)
        if not np.isfinite(weights).all() or (weights < 0).any() or weights.sum() <= 0:
            raise ValueError('combustion_shares.csv: shares must be finite, nonnegative, and have a positive total')
        weights = weights/weights.sum()
        cache[cache_key] = rows.combustion.to_numpy(), weights
        chosen[positions] = rng.choice(rows.combustion.to_numpy(), p=weights)
    result['combustion'] = chosen
    return result


def emission_multipliers(loads, network, rules, pollutant, source):
    """Most-specific matching rule, default one. Non-exhaust remains independent."""
    if rules is None:
        return np.ones(len(loads))
    keys = [c for c in rules if c != 'multiplier']
    unknown = set(keys) - (set(loads) | set(network) | {'pollutant', 'source'})
    if unknown:
        raise ValueError(f'emission_multipliers.csv: unknown keys {sorted(unknown)}')
    fields = {}
    for key in keys:
        if key in ('pollutant', 'source'): continue
        if key in loads: fields[key] = loads[key]
        else: fields[key] = loads.link_id.map(dict(zip(network.link_id.map(_zone_key), network[key])))
    factors, best = np.ones(len(loads)), np.full(len(loads), -1)
    for row in rules.to_dict('records'):
        value = float(row['multiplier'])
        if not np.isfinite(value) or value < 0:
            raise ValueError('emission_multipliers.csv: multipliers must be finite and nonnegative')
        mask, score = np.ones(len(loads), bool), 0
        for key in keys:
            if not pd.isna(row[key]):
                if key in ('pollutant', 'source'):
                    mask &= row[key] == (pollutant if key == 'pollutant' else source)
                elif pd.api.types.is_numeric_dtype(fields[key]):
                    mask &= fields[key].to_numpy() == float(row[key])
                else:
                    mask &= fields[key].map(_zone_key).to_numpy() == _zone_key(row[key])
                score += 1
        if (mask & (best == score)).any():
            raise ValueError('emission_multipliers.csv: equally specific rules overlap')
        mask &= score > best
        factors[mask], best[mask] = value, score
    return factors
