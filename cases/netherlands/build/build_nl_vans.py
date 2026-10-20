# Builds NetSy's van trip inputs for the Netherlands case from MASS-GT's
# Dutch inputs, as MASS-GT's service module (SERVICE) reads them.
#
#   trip_attributes.csv  per zone: jobs per sector and inhabitants (SEGS),
#                        distribution-centre and parcel-depot floor area
#   trip_rates.csv       SERVICE's production regressions, per day (/ YEARFACTOR)
#   trip_decay.csv       its gravity parameters and the van's cost per hour and km
#
# External zone i of MASS-GT takes the jobs and inhabitants of the i-th COROP
# region in the order of MRDHtoCOROP.txt, not of its own region; zones 35 to
# 43 take none. This reproduces SERVICE's output, bug included.

import sys
import os
from pathlib import Path

import geopandas as gpd
import pandas as pd

MASSGT = os.environ.get('MASSGT_INPUT', '/workdir/sweden/mass-gt/data/NL_main')
OUT = sys.argv[1]
YEARFACTOR = 209
COLUMNS = {'LANDBOUW': 'agriculture', 'INDUSTRIE': 'industry', 'DETAIL': 'retail', 'DIENSTEN': 'services',
           'OVERIG': 'other', '2: inwoners': 'population'}
REGRESSORS = {'DC_OPP': 'dc_surface', 'PARCEL_OPP': 'parcel_surface', 'LANDBOUW': 'agriculture',
              'INDUSTRIE': 'industry', 'DETAIL': 'retail', 'DIENSTEN': 'services', 'OVERIG': 'other',
              'INWONERS': 'population'}

massgt_zones = gpd.read_file(f'{MASSGT}/data/Zones_v6.shp', ignore_geometry=True).set_index('AREANR').sort_index()
segs = pd.read_csv(f'{MASSGT}/data/SEGS2016_verrijkt.csv').set_index('zone')
depots = gpd.read_file(f'{MASSGT}/data/parcelNodes_v2.shp', ignore_geometry=True)
depot_surface = depots.groupby(depots['AREANR'].astype(int))['Surface'].sum()

internal = segs.reindex(massgt_zones.index)[list(COLUMNS)].rename(columns=COLUMNS)
internal['dc_surface'] = massgt_zones['SurfaceDC'].astype(float)
internal['parcel_surface'] = internal.index.map(lambda z: depot_surface.get(z, 0.0))

corop = pd.read_csv(f'{MASSGT}/parameters/MRDHtoCOROP.txt', sep='\t')
order = list(corop['zone_corop'].unique())
external = []
for i, region in enumerate(order):
    members = corop.loc[corop['zone_corop'] == region, 'zone_mrdh']
    sums = segs.loc[segs.index.isin(members), list(COLUMNS)].sum().rename(COLUMNS)
    zone = 99999901 + i
    external.append({'zone_id': zone, **sums.to_dict(), 'dc_surface': 0.0, 'parcel_surface': depot_surface.get(zone, 0.0)})
attributes = pd.concat([internal.rename_axis('zone_id').reset_index(), pd.DataFrame(external)], ignore_index=True)
attributes.to_csv(f'{OUT}/trip_attributes.csv', index=False)

coefficients = pd.read_csv(f'{MASSGT}/parameters/Params_PA_SERVICE.csv', index_col=0)
rates = [(segment.lower(), REGRESSORS[name], coefficients.at[segment, name] / YEARFACTOR)
         for segment in coefficients.index for name in REGRESSORS if coefficients.at[segment, name] != 0]
pd.DataFrame(rates, columns=['segment', 'attribute', 'rate']).to_csv(f'{OUT}/trip_rates.csv', index=False)

decay = pd.read_csv(f'{MASSGT}/parameters/Params_DistanceDecay_SERVICE.txt', sep='\t').pivot(index='van_segment', columns='parameter', values='value')
van = pd.read_csv(f'{MASSGT}/parameters/Cost_VehType.txt', sep='\t').set_index('vehicle_type').loc[7]
pd.DataFrame([
    {'segment': name, 'alpha': decay.at[id_, 'alpha'], 'beta': decay.at[id_, 'beta'],
     'cost_per_hour': van['cost_per_hour'], 'cost_per_km': van['cost_per_km']}
    for id_, name in ((0, 'service'), (1, 'construction'))
]).to_csv(f'{OUT}/trip_decay.csv', index=False)
print('zones', len(attributes), '| rates', len(rates))
