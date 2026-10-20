# Builds NetSy's agent-synthesis inputs for the Netherlands (Zuid-Holland)
# case from MASS-GT's Dutch inputs, as MASS-GT's firm synthesis (FS) and
# shipment synthesis (SHIP) use them.
#
#   size_totals.csv        jobs per zone x employment sector (SEGS, rounded;
#                          distribution-centre jobs taken out of industry,
#                          and industry zeroed in transshipment-terminal zones)
#   size_classes.csv       firm-size classes per sector (national firm counts)
#   production_rates.csv   make shares per sector x NSTR commodity
#   consumption_rates.csv  use shares per sector x NSTR commodity

import sys
import os
from pathlib import Path

import geopandas as gpd
import pandas as pd

MASSGT = os.environ.get('MASSGT_INPUT', '/workdir/sweden/mass-gt/data/NL_main')
OUT = sys.argv[1]

SECTORS = {0: 'industry', 1: 'retail', 2: 'agriculture', 3: 'services', 4: 'government', 5: 'other'}
SEGS_COLUMNS = {'INDUSTRIE': 'industry', 'DETAIL': 'retail', 'LANDBOUW': 'agriculture',
                'DIENSTEN': 'services', 'OVERHEID': 'government', 'OVERIG': 'other'}
# MASS-GT's firm-size classes (dimensions/firm_size.txt) as inclusive
# whole-number bounds: it draws randint(lower, upper), upper excluded. Its
# largest class is open: a triangular draw from 100 with median 150.
SIZE_CLASSES = {0: (0, 4), 1: (5, 9), 2: (10, 19), 3: (20, 49), 4: (50, 99), 5: (100, None)}
OPEN_MEDIAN = 150
NSTR = {
    0: 'agricultural_products', 1: 'foodstuffs', 2: 'solid_mineral_fuels', 3: 'petroleum_products',
    4: 'ores_and_metal_waste', 5: 'metal_products', 6: 'minerals_and_building_materials',
    7: 'fertilizers', 8: 'chemicals', 9: 'machinery_and_manufactured_articles',
}

zones = gpd.read_file(f'{OUT}/zones.gpkg')
massgt_zones = gpd.read_file(f'{MASSGT}/data/Zones_v6.shp')

# Jobs per zone and sector, adjusted as MASS-GT's read_segs does.
segs = pd.read_csv(f'{MASSGT}/data/SEGS2016_verrijkt.csv').set_index('zone')[list(SEGS_COLUMNS)].round()
dc_jobs = pd.read_csv(f'{MASSGT}/data/distributieCentra.txt', sep='\t').groupby('zone_mrdh')['employment'].sum()
segs['INDUSTRIE'] = (segs['INDUSTRIE'] - dc_jobs.reindex(segs.index, fill_value=0)).clip(lower=0)
terminals = set(massgt_zones.loc[massgt_zones['LOGNODE'] == 1, 'AREANR'].astype(int))
segs.loc[segs.index.isin(terminals), 'INDUSTRIE'] = 0
segs = segs[segs.index.isin(zones['zone_id'])].rename(columns=SEGS_COLUMNS)
size_totals = segs.rename_axis('zone_id').reset_index().melt('zone_id', var_name='sector', value_name='size')
size_totals = size_totals[size_totals['size'] > 0].sort_values(['zone_id', 'sector'])
size_totals['size'] = size_totals['size'].astype(int)
size_totals.to_csv(f'{OUT}/size_totals.csv', index=False)

# Firm-size classes per sector, from national firm counts.
counts = pd.read_csv(f'{MASSGT}/data/FirmSizeDistributionPerSector.txt', sep='\t')
counts['sector'] = counts['employment_sector'].map(SECTORS)
counts['probability'] = counts['value'] / counts.groupby('sector')['value'].transform('sum')
counts['size_min'] = counts['firm_size'].map(lambda c: SIZE_CLASSES[c][0])
counts['size_max'] = counts['firm_size'].map(lambda c: SIZE_CLASSES[c][1]).astype('Int64')
counts['size_median'] = counts['size_max'].isna().map({True: OPEN_MEDIAN, False: None}).astype('Int64')
counts.sort_values(['employment_sector', 'firm_size'])[['sector', 'size_min', 'size_max', 'size_median', 'probability']].to_csv(
    f'{OUT}/size_classes.csv', index=False)

# Make and use shares per sector and commodity; zero shares are left out.
for source, name in (('MakeDistribution', 'production_rates'), ('UseDistribution', 'consumption_rates')):
    shares = pd.read_csv(f'{MASSGT}/data/{source}.txt', sep='\t')
    shares = shares[shares['share'] > 0].assign(
        sector=lambda t: t['employment_sector'].map(SECTORS), resource=lambda t: t['nstr'].map(NSTR))
    shares.sort_values(['nstr', 'employment_sector'])[['sector', 'resource', 'share']].rename(
        columns={'share': 'rate'}).to_csv(f'{OUT}/{name}.csv', index=False)

print('strata', len(size_totals), 'jobs', size_totals['size'].sum(), '| classes', len(counts),
      )
