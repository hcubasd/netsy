"""Facility-mediated parcel legs, including UCC and microhub operations.

Selection, eligibility, operator collaboration, vehicle shares, and radius
rules are scenario tables. Physical parcels are counted at final deliveries;
leg quantities additionally count transshipment, never extra customer demand.
"""
import numpy as np
import pandas as pd
from netsy.synth.agents import _zone_key


def parcel_routing(demand, zones, facilities, skims, settings, shares, rng):
    if not {"setting", "value"} <= set(settings) or settings.setting.duplicated().any():
        raise ValueError("parcel_routing_settings.csv: unique setting/value rows are required")
    if not {"vehicle", "share"} <= set(shares):
        raise ValueError("parcel_routing_vehicles.csv: vehicle and share are required")
    cfg = dict(zip(settings.setting, settings.value))
    allowed = {'flag_column', 'flag_min', 'facility_type', 'probability', 'selection', 'operator_column', 'area_column', 'pool_operators', 'default_vehicle', 'inbound_vehicle'}
    if set(cfg)-allowed: raise ValueError(f"parcel_routing_settings.csv: unknown settings {sorted(set(cfg)-allowed)}")
    required = {'flag_column', 'facility_type', 'probability', 'selection'}
    if required-set(cfg):
        raise ValueError(f"parcel_routing_settings.csv: missing settings {sorted(required-set(cfg))}")
    if cfg['selection'] not in ('minimum_detour', 'nearest'):
        raise ValueError('parcel routing selection must be minimum_detour or nearest')
    probability = float(cfg['probability'])
    if not 0 <= probability <= 1:
        raise ValueError('parcel routing probability must be in [0,1]')
    flag = cfg['flag_column']; threshold=float(cfg.get('flag_min', 1))
    if flag not in zones:
        raise ValueError(f'zones.gpkg: missing flag {flag!r}')
    indexed = zones.set_index(zones.zone_id.map(_zone_key))
    hubs = facilities[facilities.facility_type == cfg['facility_type']].copy()
    if hubs.empty:
        raise ValueError('facilities.gpkg: no eligible routing facilities')
    ids, _, distance = skims; ix={z:i for i,z in enumerate(ids)}
    weights=pd.to_numeric(shares.share, errors='raise').to_numpy(float)
    if not np.isfinite(weights).all() or (weights<0).any() or weights.sum()<=0:
        raise ValueError('parcel_routing_vehicles.csv: nonnegative vehicle shares must have a positive total')
    if shares.vehicle.duplicated().any():
        raise ValueError('parcel_routing_vehicles.csv: vehicle keys must be unique')
    output=[]
    for parent, row in enumerate(demand.to_dict('records'), 1):
        origin,destination=_zone_key(row['origin_zone_id']),_zone_key(row['destination_zone_id'])
        count=float(row['parcels'])
        if count<0 or not np.isfinite(count) or count != int(count):
            raise ValueError('parcel_demand.csv: parcels must be nonnegative whole numbers')
        moved = int(rng.binomial(int(count),probability)) if float(indexed.loc[destination,flag])>=threshold else 0
        candidates=hubs
        operator_column=cfg.get('operator_column')
        if operator_column and not pd.isna(operator_column):
            if operator_column not in candidates:
                raise ValueError(f'facilities.gpkg: missing operator column {operator_column!r}')
            candidates=candidates[candidates[operator_column].map(_zone_key)==_zone_key(row['operator'])]
        area_column=cfg.get('area_column')
        if area_column and not pd.isna(area_column):
            allowed=indexed.loc[destination,area_column]
            candidates=candidates[candidates.zone_id.map(_zone_key).map(indexed[area_column])==allowed]
        common=dict(row,parent_demand_id=parent,vehicle=cfg.get('default_vehicle','van'))
        if int(count)-moved:
            output.append(dict(common,parcels=int(count)-moved,leg='direct',final_delivery=True))
        if not moved:
            continue
        if candidates.empty:
            raise ValueError(f'no eligible facility for zone {destination} and operator {row["operator"]}')
        indices=np.array([ix[_zone_key(z)] for z in candidates.zone_id])
        costs=distance[indices,ix[destination]].astype(float)
        if cfg['selection']=='minimum_detour': costs += distance[ix[origin],indices]
        hub=candidates.iloc[int(np.argmin(costs))]; hz=_zone_key(hub.zone_id)
        output.append(dict(common, destination_zone_id=hub.zone_id,parcels=moved,leg='inbound',final_delivery=False,vehicle=cfg.get('inbound_vehicle',common['vehicle'])))
        quantities=rng.multinomial(moved,weights/weights.sum())
        for vehicle,quantity in zip(shares.to_dict('records'),quantities):
            if not quantity: continue
            name=vehicle['vehicle']
            radius=vehicle.get('maximum_distance')
            if radius is not None and not pd.isna(radius) and distance[ix[hz],ix[destination]]>float(radius):
                name=vehicle.get('fallback_vehicle')
                if name is None or pd.isna(name): raise ValueError('radius-limited vehicle needs fallback_vehicle')
            output.append(dict(common,origin_zone_id=hub.zone_id,facility_id=hub.facility_id,
                               parcels=int(quantity),vehicle=name,leg='outbound',final_delivery=True,
                               delivery_group=hub.facility_id if str(cfg.get('pool_operators',0)) in ('1','1.0','true') else row['facility_id'],
                               demand_operator=row['operator'],operator='collaborative' if str(cfg.get('pool_operators',0)) in ('1','1.0','true') else row['operator']))
    return pd.DataFrame(output)
