# Builds NetSy's commodity-matrix inputs for the Netherlands case from
# MASS-GT's Dutch inputs, as MASS-GT's spatial interaction freight module
# (SIF) reads them.
#
#   location_attributes.csv    jobs per sector (SEGS) and distribution-centre
#                              floor area per NUTS3 region
#   marginal_coefficients.csv  SIF's production and attraction regressions
#   od_prior.csv               the base commodity matrix (tonnes per year)

import sys
import os
from pathlib import Path

import pandas as pd

MASSGT = os.environ.get('MASSGT_INPUT', '/workdir/sweden/mass-gt/data/NL_main')
OUT = sys.argv[1]
SECTORS = {'INDUSTRIE': 'industry', 'DETAIL': 'retail', 'LANDBOUW': 'agriculture',
           'DIENSTEN': 'services', 'OVERHEID': 'government', 'OVERIG': 'other'}
ATTRIBUTES = {'industrie': 'industry', 'detail': 'retail', 'landbouw': 'agriculture', 'diensten': 'services',
              'overheid': 'government', 'overig': 'other', 'dc_opp': 'dc_surface'}
NSTR = {
    0: 'agricultural_products', 1: 'foodstuffs', 2: 'solid_mineral_fuels', 3: 'petroleum_products',
    4: 'ores_and_metal_waste', 5: 'metal_products', 6: 'minerals_and_building_materials',
    7: 'fertilizers', 8: 'chemicals', 9: 'machinery_and_manufactured_articles',
}

# Jobs per NUTS3 region: the SEGS zones whose region is known, summed.
regions = pd.read_csv(f'{MASSGT}/parameters/MRDHtoNUTS3.txt', sep='\t').set_index('zone_mrdh')['zone_nuts3']
segs = pd.read_csv(f'{MASSGT}/data/SEGS2016_verrijkt.csv').set_index('zone')
segs = segs[segs.index.isin(regions.index)]
attributes = segs[list(SECTORS)].groupby(regions.loc[segs.index].to_numpy()).sum().rename(columns=SECTORS)
surface = pd.read_csv(f'{MASSGT}/data/DC_OPP_NUTS3.txt', sep='\t').set_index('zone_nuts')['surface_m2']
attributes['dc_surface'] = attributes.index.map(lambda r: surface.get(r, 0)).astype(float)
# Belgium, Germany and France keep their totals of the base matrix.
attributes = pd.concat([attributes, pd.DataFrame(index=['BE', 'DE', 'FR'], columns=attributes.columns)])
attributes.rename_axis('location_id').reset_index().to_csv(f'{OUT}/location_attributes.csv', index=False)

rows = []
for side, name in (('production', 'PROD'), ('attraction', 'ATTR')):
    params = pd.read_csv(f'{MASSGT}/parameters/Params_PA_{name}.txt', sep='\t')
    rows.append(params.assign(resource=params['nstr'].map(NSTR), attribute=params['parameter'].map(ATTRIBUTES))
                .set_index(['resource', 'attribute'])['value'].rename(side))
coefficients = pd.concat(rows, axis=1).fillna(0).reset_index()
coefficients.to_csv(f'{OUT}/marginal_coefficients.csv', index=False)

# The base matrix; only its cells between listed locations are balanced.
matrix = pd.read_csv(f'{MASSGT}/data/CommodityMatrixNUTS3.txt', sep='\t')
pd.DataFrame({
    'resource': matrix['nstr'].map(NSTR), 'origin_location_id': matrix['orig_nuts'],
    'destination_location_id': matrix['dest_nuts'], 'weight': matrix['tonnes_year'],
}).to_csv(f'{OUT}/od_prior.csv', index=False)
print('locations', len(attributes), '| coefficients', len(coefficients), '| prior', len(matrix), round(matrix['tonnes_year'].sum()))
