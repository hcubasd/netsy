# Builds NetSy's shipment-synthesis inputs for the Netherlands (Zuid-Holland)
# case from MASS-GT's Dutch inputs, as MASS-GT's shipment synthesis (SHIP)
# reads them with the NL_REF settings (YEARFACTOR 209, no day-to-week factor,
# no nearest-DC rule, no logistic-segment factors, parcel growth 1).
#
#   zones.gpkg             the study-area zones plus MASS-GT's 37 external zones,
#                          with the region (superzone) of each and the urban-density
#                          classes its delivery-time choice uses
#   facilities.gpkg        distribution centres, transshipment terminals and
#                          parcel depots
#   skims.omx              MASS-GT's time (h) and distance (km) skims
#   shipment_totals.csv    tonnes per day per region pair, flow type, NSTR resource
#                          and logistic segment, as SHIP derives them from the
#                          commodity matrix (od_flows.csv), plus its corrections, keyed also by
#                          MASS-GT's flow-type id
#   flow_types.csv, distance_decay.csv, shipment_sizes.csv, shipment_vehicles.csv,
#   vehicle_choice.csv, delivery_windows.csv, delivery_choice.csv

import sys
import os
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point, box

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src'))
from netsy.helpers.skims import write_skims  # noqa: E402

MASSGT = os.environ.get('MASSGT_INPUT', '/workdir/sweden/mass-gt/data/NL_main')
DIMENSIONS = os.environ.get('MASSGT_DIMENSIONS', '/workdir/sweden/mass-gt/tfs-harmony/dimensions')
OUT = sys.argv[1]
YEARFACTOR = 209
STUDY_AREA = 'Zuid-Holland'

NSTR = {
    0: 'agricultural_products', 1: 'foodstuffs', 2: 'solid_mineral_fuels', 3: 'petroleum_products',
    4: 'ores_and_metal_waste', 5: 'metal_products', 6: 'minerals_and_building_materials',
    7: 'fertilizers', 8: 'chemicals', 9: 'machinery_and_manufactured_articles',
}
SEGMENTS = {
    0: 'food', 1: 'miscellaneous', 2: 'temperature_controlled', 3: 'facility', 4: 'construction',
    5: 'waste', 6: 'parcel_consolidated', 7: 'dangerous',
}
PARCELS = 6
VEHICLES = {
    0: 'truck_small', 1: 'truck_medium', 2: 'truck_large', 3: 'truck_trailer_small',
    4: 'truck_trailer_large', 5: 'tractor_trailer', 6: 'special_vehicle',
}
SIZE_CLASSES = ['under_3t', '3_to_6t', '6_to_10t', '10_to_20t', '20_to_30t', 'over_30t']
# MASS-GT's flow types 1 to 12, as NetSy flow types. External flow types are
# split by direction: SHIP draws an export's internal end with decay, and an
# import's internal end, too, from the external zone.
INTERNAL = {
    1: ('direct', 'agent', 'agent'),
    2: ('to_distribution_centre', 'agent', 'distribution_centre'),
    3: ('from_distribution_centre', 'distribution_centre', 'agent'),
    4: ('to_terminal', 'agent', 'terminal'),
    5: ('between_distribution_centres', 'distribution_centre', 'distribution_centre'),
    6: ('from_terminal', 'terminal', 'agent'),
    7: ('distribution_centre_to_terminal', 'distribution_centre', 'terminal'),
    8: ('terminal_to_distribution_centre', 'terminal', 'distribution_centre'),
    9: ('between_terminals', 'terminal', 'terminal'),
}
EXTERNAL = {10: ('direct', 'agent'), 11: ('distribution_centre', 'distribution_centre'), 12: ('terminal', 'terminal')}

data, parameters = f'{MASSGT}/data', f'{MASSGT}/parameters'

# ------------------------------------------------------------------ zones
zones = gpd.read_file(f'{OUT}/zones.gpkg')
# The study-area zones, without what an earlier build added.
zones = zones[zones['zone_id'] < 99999900][['zone_id', 'zone_name', 'municipality', 'geometry']]
massgt_zones = gpd.read_file(f'{data}/Zones_v6.shp').set_index('AREANR')
segs = pd.read_csv(f'{data}/SEGS2016_verrijkt.csv').set_index('zone').reindex(massgt_zones.index)
density = (segs['1: woningen'] + segs['9: arbeidspl_totaal']) / (massgt_zones['area'] / 100000)
density_class = pd.cut(density, [-np.inf, 500, 1000, 1500, 2500, np.inf], right=False, labels=[1, 2, 3, 4, 5]).astype(int)
lognode = massgt_zones['LOGNODE'].astype(int)
zones['region'] = STUDY_AREA
zones['terminal_density_class'] = zones['zone_id'].map(density_class.where(lognode == 1, 0)).astype(int)
zones['regular_density_class'] = zones['zone_id'].map(density_class.where(lognode == 0, 0)).astype(int)
# TOUR's urbanized zones (house or job density above about the top 10%) and
# transshipment-terminal zones.
urban = (segs['1: woningen'] / massgt_zones['area'] > 0.0075) | (segs['9: arbeidspl_totaal'] / massgt_zones['area'] > 0.0050)
zones['urban'] = zones['zone_id'].map(urban.astype(int)).astype(int)
zones['terminal_zone'] = zones['zone_id'].map((lognode == 1).astype(int)).astype(int)
zones['x'] = zones['zone_id'].map(massgt_zones['X'])
zones['y'] = zones['zone_id'].map(massgt_zones['Y'])
zones['external'] = 0
# MASS-GT's external zones (superzones), at its coordinates. Superzones 25 to
# 30 are Zuid-Holland's own COROP regions: MASS-GT gives them no polygon and
# no freight, but its van trips use them, so they are 1 km squares at their
# coordinates.
super_coordinates = pd.read_csv(f'{data}/SupCoordinatesID.txt', sep='\t').set_index('zone_mrdh')
external = gpd.read_file(f'{data}/ExternalZones.shp').set_crs(zones.crs)
names = dict(zip(external['AREANR'].astype(int), external['OMSCHRIJVI']))
geometry = dict(zip(external['AREANR'].astype(int), external.geometry))
INSIDE = {99999925: 'Agglomeratie Leiden en Bollenstreek', 99999926: "Agglomeratie 's-Gravenhage",
          99999927: 'Delft en Westland', 99999928: 'Oost-Zuid-Holland', 99999929: 'Groot-Rijnmond',
          99999930: 'Zuidoost-Zuid-Holland'}
for zone, name in INSIDE.items():
    x, y = super_coordinates.loc[zone, ['x_coord', 'y_coord']]
    names[zone], geometry[zone] = name, box(x - 500, y - 500, x + 500, y + 500)
ids = sorted(names)
external = gpd.GeoDataFrame({
    'zone_id': ids, 'zone_name': [names[z] for z in ids], 'municipality': None, 'region': [names[z] for z in ids],
    'terminal_density_class': 0, 'regular_density_class': 0, 'urban': 0, 'terminal_zone': 0,
    'x': super_coordinates.loc[ids, 'x_coord'].to_numpy(float), 'y': super_coordinates.loc[ids, 'y_coord'].to_numpy(float),
    'external': 1,
}, geometry=[geometry[z] for z in ids], crs=zones.crs)
zones = pd.concat([zones, external], ignore_index=True)
zones.to_file(f'{OUT}/zones.gpkg', driver='GPKG')
region_of = dict(zip(zones['zone_id'], zones['region']))

# ------------------------------------------------------------------ facilities
dcs = pd.read_csv(f'{data}/distributieCentra.txt', sep='\t')
dcs = dcs[~dcs['zone_mrdh'].isna()].reset_index(drop=True)
terminals = massgt_zones[lognode == 1].sort_index()
# All depots, as parcel demand chooses among them; only those in the study
# area take part in SHIP's consolidated parcel flows.
depots = gpd.read_file(f'{data}/parcelNodes_v2.shp').sort_values('id').reset_index(drop=True)
internal_depot = depots['AREANR'] < 99999900
cep = pd.read_csv(f'{data}/CEPshares.txt', sep='\t').set_index('courier')
counts = depots.loc[internal_depot, 'CEP'].value_counts()
for column in ('share_nl', 'share_total'):
    cep.loc[cep.index.map(lambda c: counts.get(c, 0) <= 1), column] = 0
surface = depots['Surface'].where(internal_depot, 0.0)
surface_share = surface / surface.groupby(depots['CEP']).transform('sum')
facilities = pd.concat([
    pd.DataFrame({
        'facility_id': [f'dc_{i}' for i in dcs.index], 'facility_type': 'distribution_centre',
        'zone_id': dcs['zone_mrdh'].astype(int), 'size': dcs['surface_m2'].astype(float),
        'x': dcs['x_coord'], 'y': dcs['y_coord'],
    }),
    pd.DataFrame({
        'facility_id': [f'terminal_{z}' for z in terminals.index], 'facility_type': 'terminal',
        'zone_id': terminals.index.astype(int), 'size': terminals['area'].astype(float),
        'x': terminals['X'], 'y': terminals['Y'],
    }),
    pd.DataFrame({
        'facility_id': [f'depot_{int(i)}' for i in depots['id']], 'facility_type': 'parcel_depot',
        'zone_id': depots['AREANR'].astype(int), 'size': depots['Surface'].astype(float),
        'operator': depots['CEP'],
        'internal_share': depots['CEP'].map(cep['share_nl']) * surface_share,
        'total_share': depots['CEP'].map(cep['share_total']) * surface_share,
        'x': depots.geometry.x, 'y': depots.geometry.y,
    }),
], ignore_index=True)
facilities = gpd.GeoDataFrame(
    facilities.drop(columns=['x', 'y']), geometry=gpd.points_from_xy(facilities['x'], facilities['y']), crs=zones.crs)
facilities.to_file(f'{OUT}/facilities.gpkg', driver='GPKG')

# ------------------------------------------------------------------ skims
super_zones = pd.read_csv(f'{data}/SupCoordinatesID.txt', sep='\t')
skim_ids = list(massgt_zones.sort_index().index.astype(int)) + list(super_zones['zone_mrdh'].astype(int))
count = len(skim_ids)
time = np.fromfile(f'{data}/skimTijd_REF.mtx', dtype=np.float32)[1:].reshape(count, count) / 3600
distance = np.fromfile(f'{data}/skimAfstand_REF.mtx', dtype=np.float32)[1:].reshape(count, count) / 1000
write_skims(f'{OUT}/skims.omx', skim_ids, time, distance)

# ------------------------------------------------------------------ totals
tonnes = pd.read_csv(f'{data}/nstrToLogisticSegment.txt', sep='\t').pivot(index='nstr', columns='logistic_segment', values='tonnes')
tonnes = tonnes[list(SEGMENTS)]
nstr_to_ls = tonnes.div(tonnes.sum(axis=1), axis=0).fillna(0)
ls_to_nstr = tonnes.div(tonnes.sum(axis=0), axis=1).fillna(0)
shares = pd.read_csv(f'{parameters}/LogFlowtype_Shares.txt', sep='\t').pivot(index='logistic_segment', columns='flow_type', values='share').fillna(0)

# Tonnes per day per superzone pair and logistic segment (SHIP's
# get_commodity_matrix): NSTR tonnes by NUTS3 pair, converted to segments.
regions = pd.read_csv(f'{parameters}/NUTS3toMRDH.txt', sep='\t')
superzone = dict(zip(regions['zone_nuts3'], regions['zone_mrdh'] - 99999900))
# The commodity matrix: NetSy's od-flows.csv, as SIF writes it.
flows = pd.read_csv(f'{OUT}/od_flows.csv')
matrix = pd.DataFrame({
    'ORIG': flows['origin_location_id'], 'DEST': flows['destination_location_id'],
    'NSTR': flows['resource'].map({name: nstr for nstr, name in NSTR.items()}), 'TonnesYear': flows['quantity'],
})
matrix = matrix[matrix['ORIG'].isin(superzone) & matrix['DEST'].isin(superzone)]
matrix = matrix.assign(i=matrix['ORIG'].map(superzone), j=matrix['DEST'].map(superzone), weight=matrix['TonnesYear'] / YEARFACTOR)
by_nstr = matrix.groupby(['i', 'j', 'NSTR'])['weight'].sum().unstack('NSTR', fill_value=0).reindex(columns=list(NSTR), fill_value=0)
by_segment = by_nstr @ nstr_to_ls  # (i, j) x segment
name_of = dict(zip(super_zones['zone_mrdh'] - 99999900, [None] * len(super_zones)))
for zone_id, region in region_of.items():
    if zone_id > 99999900:
        name_of[zone_id - 99999900] = region


def split(demand, flow_type_of, origin, destination, rows, extra=()):
    # Demand per segment, split by flow-type shares and back to NSTR by
    # SHIP's lsToNstr, as its synthesis loops do.
    for ls, segment in SEGMENTS.items():
        for massgt_flow, flow_type in flow_type_of(ls).items():
            for nstr, resource in NSTR.items():
                quantity = demand.get(ls, 0.0) * shares.at[ls, massgt_flow] * ls_to_nstr.at[nstr, ls]
                if quantity > 0:
                    rows.append((origin, destination, *extra, flow_type, resource, segment, massgt_flow, quantity))


rows = []
internal = by_segment.loc[(0, 0)].to_dict() if (0, 0) in by_segment.index else {}
split(internal, lambda ls: {f: ('parcel_between_depots' if ls == PARCELS else INTERNAL[f][0]) for f in INTERNAL}, STUDY_AREA, STUDY_AREA, rows)
for k, name in name_of.items():
    if name is None:
        continue
    # SHIP reads its exports from the commodity matrix's external-to-study
    # cells and its imports from the study-to-external cells.
    exports = by_segment.loc[(k, 0)].to_dict() if (k, 0) in by_segment.index else {}
    imports = by_segment.loc[(0, k)].to_dict() if (0, k) in by_segment.index else {}
    split(exports, lambda ls: {f: ('parcel_export' if ls == PARCELS else f'export_{EXTERNAL[f][0]}') for f in EXTERNAL}, STUDY_AREA, name, rows)
    split(imports, lambda ls: {f: ('parcel_import' if ls == PARCELS else f'import_{EXTERNAL[f][0]}') for f in EXTERNAL}, name, STUDY_AREA, rows)
# MASS-GT moves each flow type's share as its own total, even where, as for
# parcels, flow types share a definition; massgt_flow_type keeps them apart.
totals = pd.DataFrame(rows, columns=['origin_region', 'destination_region', 'flow_type', 'resource', 'segment', 'massgt_flow_type', 'quantity'])

corrections = []
for row in pd.read_csv(f'{data}/CorrectionsTonnes.txt', sep='\t').to_dict('records'):
    origin, destination, ls = int(row['orig_mrdh']), int(row['dest_mrdh']), int(row['logistic_segment'])
    flow_type = {(True, True): 'correction_between_zones', (True, False): 'correction_from_zone', (False, True): 'correction_to_zone'}[(origin != -1, destination != -1)]
    for nstr, resource in NSTR.items():
        if ls_to_nstr.at[nstr, ls] > 0:
            corrections.append((
                STUDY_AREA, STUDY_AREA, origin if origin != -1 else None, destination if destination != -1 else None,
                flow_type, resource, SEGMENTS[ls], 1, row['tonnes_day'] * ls_to_nstr.at[nstr, ls],
            ))
columns = ['origin_region', 'destination_region', 'origin_zone_id', 'destination_zone_id', 'flow_type', 'resource', 'segment', 'massgt_flow_type', 'quantity']
totals = pd.concat([totals.assign(origin_zone_id=None, destination_zone_id=None)[columns], pd.DataFrame(corrections, columns=columns)])
totals['origin_zone_id'] = totals['origin_zone_id'].astype('Int64')
totals['destination_zone_id'] = totals['destination_zone_id'].astype('Int64')
totals.to_csv(f'{OUT}/shipment_totals.csv', index=False)

# ------------------------------------------------------------------ flow types
flow_rows = [(name, origin, destination, 'origin', None, None, None, None) for name, origin, destination in INTERNAL.values()]
for kind, end in EXTERNAL.values():
    flow_rows.append((f'export_{kind}', end, 'zone', 'origin', None, None, None, None))
    flow_rows.append((f'import_{kind}', 'zone', end, 'destination', None, None, None, None))
flow_rows += [
    ('parcel_between_depots', 'parcel_depot', 'parcel_depot', None, 'size', 'internal_share', 'operator', 'true'),
    ('parcel_export', 'parcel_depot', 'zone', None, 'total_share', None, None, None),
    ('parcel_import', 'zone', 'parcel_depot', None, None, 'total_share', None, None),
    ('correction_to_zone', 'agent', 'zone', 'origin', None, None, None, None),
    ('correction_from_zone', 'zone', 'agent', None, None, None, None, None),
    ('correction_between_zones', 'zone', 'zone', None, None, None, None, None),
]
pd.DataFrame(flow_rows, columns=[
    'flow_type', 'origin', 'destination', 'decay', 'origin_weight', 'destination_weight', 'same', 'distinct',
]).to_csv(f'{OUT}/flow_types.csv', index=False)

# ------------------------------------------------------------------ choices
decay = pd.read_csv(f'{parameters}/Params_DistanceDecay_FREIGHT.txt', sep='\t').set_index('parameter')['value']
sourcing = pd.read_csv(f'{parameters}/Cost_Sourcing.txt', sep='\t').iloc[0]
pd.DataFrame([{
    'alpha': decay['alpha'], 'beta': decay['beta'],
    'cost_per_hour': sourcing['cost_per_hour'], 'cost_per_km': sourcing['cost_per_km'],
}]).to_csv(f'{OUT}/distance_decay.csv', index=False)

sizes = pd.read_csv(f'{DIMENSIONS}/shipment_size.txt', sep='\t')
pd.DataFrame({'size_class': SIZE_CLASSES, 'quantity': sizes['Median']}).to_csv(f'{OUT}/shipment_sizes.csv', index=False)

costs = pd.read_csv(f'{parameters}/Cost_VehType.txt', sep='\t').set_index('vehicle_type')
capacity = pd.read_csv(f'{parameters}/CarryingCapacity.txt', sep='\t').set_index('vehicle_type')['capacity_kg'] / 1000
pd.DataFrame([
    {'vehicle': name, 'capacity': capacity[v], 'cost_per_hour': costs.at[v, 'cost_per_hour'], 'cost_per_km': costs.at[v, 'cost_per_km']}
    for v, name in VEHICLES.items()
]).to_csv(f'{OUT}/shipment_vehicles.csv', index=False)

# SHIP's draw_vehicle_type_and_shipment_size, term by term. Its from-DC and
# to-DC indicators are set for distribution centres and parcel depots.
params = pd.read_csv(f'{parameters}/Params_ShipSize_VehType.txt', sep='\t')
params = params.set_index(['nstr', 'parameter'])['value']
choice = []
for nstr, resource in NSTR.items():
    p = params[nstr]
    choice += [(resource, VEHICLES[v], 'constant', p[f'ASC_VT_{v + 1}']) for v in VEHICLES]
    choice += [(resource, None, 'transport_cost', p['B_TransportCosts']), (resource, None, 'size', p['B_InventoryCosts'])]
    for kind in ('distribution_centre', 'parcel_depot'):
        choice.append((resource, VEHICLES[0], f'origin:{kind}', p['B_FromDC']))
        choice += [(resource, VEHICLES[v], f'destination:{kind}', p['B_ToDC']) for v in (3, 4, 5)]
    choice += [(resource, VEHICLES[v], 'distance_above:100', p['B_LongHaul_TruckTrailer']) for v in (3, 4)]
    choice.append((resource, VEHICLES[5], 'distance_above:100', p['B_LongHaul_TractorTrailer']))
pd.DataFrame(choice, columns=['resource', 'vehicle', 'term', 'value']).to_csv(f'{OUT}/vehicle_choice.csv', index=False)

# SHIP's draw_delivery_times, per logistic segment. Its log(2 x duration)
# differs from log(duration) by a constant that a logit ignores.
tod = pd.read_csv(f'{parameters}/Params_TOD.csv', index_col=0)
windows, delivery = [], []
for ls, segment in SEGMENTS.items():
    column = tod[str(ls + 1)]
    for t in range(1, 6):
        if '_' not in str(column[f'Interval_{t}']):
            continue
        start, end = (int(x) for x in column[f'Interval_{t}'].split('_'))
        window = f'{start}-{end}'
        windows.append((segment, window, start, end))
        terms = {
            'constant': f'ASC_{t}',
            'destination:terminal_density_class': f'ToTT_{t}', 'destination:regular_density_class': f'ToPC_{t}',
            'origin:terminal_density_class': f'FromTT_{t}', 'origin:regular_density_class': f'FromPC_{t}',
            'vehicle:truck_small': f'VT_SmallTruck_{t}', 'vehicle:truck_medium': f'VT_MediumTruck_{t}',
            'vehicle:truck_trailer_small': f'VT_TruckTrailer_{t}', 'vehicle:truck_trailer_large': f'VT_TruckTrailer_{t}',
            'vehicle:tractor_trailer': f'VT_TractorTrailer_{t}',
        }
        delivery += [(segment, window, term, float(column[name])) for term, name in terms.items() if float(column[name]) != 0]
    delivery.append((segment, None, 'log_duration', float(column['DurTimePeriod'])))
pd.DataFrame(windows, columns=['segment', 'window', 'start', 'end']).to_csv(f'{OUT}/delivery_windows.csv', index=False)
pd.DataFrame(delivery, columns=['segment', 'window', 'term', 'value']).to_csv(f'{OUT}/delivery_choice.csv', index=False)

# ------------------------------------------------------------------ tours
pd.DataFrame([
    ('independent_carriers', 100), ('max_shipments', 10), ('max_duration', 9), ('max_proximity', 100),
    ('capacity_slack', 1.1), ('mean_dwell_time', 0.25),
    ('carrier_facility_type', 'distribution_centre'), ('same_stratum', 'segment'),
], columns=['setting', 'value']).to_csv(f'{OUT}/tour_settings.csv', index=False)
# TOUR's end-tour logits, term by term. Its transshipment, DC and urban
# indicators look at the tour's first shipment.
common = {
    'ASC_ET': ['constant'], 'Transshipment': ['zone:terminal_zone'],
    'DC loading': ['origin:distribution_centre'], 'DC unloading': ['destination:distribution_centre'],
    'Urban': ['zone:urban'], 'VT0': ['vehicle:truck_small'], 'VT1': ['vehicle:truck_medium'],
    'NSTR0': [f'resource:{NSTR[0]}'], 'NSTR1': [f'resource:{NSTR[1]}'],
    'NSTR2to5': [f'resource:{NSTR[n]}' for n in (2, 3, 4, 5)],
    'NSTR6': [f'resource:{NSTR[6]}'], 'NSTR7': [f'resource:{NSTR[7]}'], 'NSTR8': [f'resource:{NSTR[8]}'],
}
for name, extra in (
    ('EndTourFirst', {'Tour duration': ['sqrt_duration'], 'Capacity utilization': ['squared_utilization']}),
    ('EndTourLater', {'Tour duration': ['duration'], 'Capacity utilization': ['utilization'], 'Prox': ['proximity'], 'Stops': ['log_stops']}),
):
    params = pd.read_csv(f'{parameters}/Params_{name}.txt', sep='\t').set_index('parameter')['value']
    terms = {**common, **extra}
    rows = [(term, params[parameter]) for parameter in params.index for term in terms[parameter]]
    out = 'end_tour_first' if name == 'EndTourFirst' else 'end_tour_later'
    pd.DataFrame(rows, columns=['term', 'value']).to_csv(f'{OUT}/{out}.csv', index=False)

print('zones', len(zones), '| facilities', facilities['facility_type'].value_counts().to_dict(),
      '| totals', len(totals), round(totals['quantity'].sum()), 't/day')
