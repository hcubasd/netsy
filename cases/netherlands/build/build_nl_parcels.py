# Builds NetSy's parcel-demand inputs for the Netherlands case from MASS-GT's
# Dutch inputs, as MASS-GT's parcel demand module (PARCEL_DMND) reads them
# with the NL_REF settings.
#
#   parcel_attributes.csv  jobs per study-area zone (SEGS)
#   parcel_rates.csv       business parcels per job (PARCELS_PER_EMPL / PARCELS_SUCCESS_B2B)
#   population.csv         persons per zone, age group and income group, with
#                          the zone's urbanization (SEGS)
#   order_levels.csv       the ordered logit's parcel levels and thresholds
#   order_utility.csv      its age, income and urbanization terms
#   operator_shares.csv    couriers' market shares
#   parcel_settings.csv    a 60-day period, scaled to 0.05168 parcels per person
#   delivery_settings.csv, delivery_departures.csv   PARCEL_SCHD's van load,
#                          drop time and departure hours

import sys
import os
from pathlib import Path

import geopandas as gpd
import pandas as pd

MASSGT = os.environ.get('MASSGT_INPUT', '/workdir/sweden/mass-gt/data/NL_main')
OUT = sys.argv[1]
AGES, INCOMES = range(2, 11), range(1, 7)

study = gpd.read_file(f'{OUT}/zones.gpkg', ignore_geometry=True)
study = study.loc[study['zone_id'] < 99999900, 'zone_id']
segs = pd.read_csv(f'{MASSGT}/data/SEGS2016_verrijkt.csv').set_index('zone').reindex(study).fillna(0)

pd.DataFrame({'zone_id': segs.index, 'jobs': segs['9: arbeidspl_totaal']}).to_csv(f'{OUT}/parcel_attributes.csv', index=False)
pd.DataFrame({'attribute': ['jobs'], 'rate': [0.041 / 0.95]}).to_csv(f'{OUT}/parcel_rates.csv', index=False)

# Persons per age and income group: the zone's people of an age, as a share
# of its people, times its people of an income group, as MASS-GT spreads them.
rows = []
for zone, row in segs.iterrows():
    people = row['2: inwoners']
    for age in AGES:
        for income in INCOMES:
            persons = row[f'KLEEFT_{age}'] / people * row[f'HHINK_{income}'] if people > 0 else 0.0
            rows.append((zone, age, income, int(row['STED']), persons))
pd.DataFrame(rows, columns=['zone_id', 'age_group', 'income_group', 'urbanization', 'persons']).to_csv(
    f'{OUT}/population.csv', index=False)

params = pd.read_csv(f'{MASSGT}/parameters/Params_EcommerceDemand.csv', encoding='utf-8-sig')
levels = params[params['Variable'] == 'mu']
pd.DataFrame({
    'level': levels['Variable level'].astype(int), 'quantity': levels['Parcels'].astype(float),
    'threshold': list(levels['Estimate'].astype(float))[:-1] + [None],
}).to_csv(f'{OUT}/order_levels.csv', index=False)
terms = []
for _, row in params[params['Variable'] != 'mu'].iterrows():
    column = {'KLEEFT2': 'age_group', 'HHBRUTOINK2': 'income_group', 'STED_GM': 'urbanization'}[row['Variable']]
    terms.append({column: int(row['Variable level']), 'value': float(row['Estimate'])})
pd.DataFrame(terms, columns=['age_group', 'income_group', 'urbanization', 'value']).astype(
    {'age_group': 'Int64', 'income_group': 'Int64', 'urbanization': 'Int64'}).to_csv(f'{OUT}/order_utility.csv', index=False)

cep = pd.read_csv(f'{MASSGT}/data/CEPshares.txt', sep='\t')
pd.DataFrame({'operator': cep['courier'], 'share': cep['share_total']}).to_csv(f'{OUT}/operator_shares.csv', index=False)
pd.DataFrame([('period', 60), ('per_person', 0.05168), ('depot_type', 'parcel_depot'), ('operator_column', 'operator')],
             columns=['setting', 'value']).to_csv(f'{OUT}/parcel_settings.csv', index=False)
# PARCEL_SCHD: vans of 180 parcels, 120 s per parcel dropped, departures by
# MASS-GT's hourly distribution, and TRAF's 50% load for emissions.
pd.DataFrame([('max_load', 180), ('drop_time', 120 / 3600), ('vehicle', 'van'), ('segment', 'parcel_deliveries'),
              ('utilization', 0.5)], columns=['setting', 'value']).to_csv(f'{OUT}/delivery_settings.csv', index=False)
pd.read_csv(f'{MASSGT}/data/departureTimeParcelsCDF.txt', sep='\t').to_csv(f'{OUT}/delivery_departures.csv', index=False)
print('zones', len(segs), '| population cells', len(rows), '| persons', round(sum(r[-1] for r in rows)))
