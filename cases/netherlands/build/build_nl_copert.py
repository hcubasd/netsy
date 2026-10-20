# Builds NetSy's COPERT V inputs for the Netherlands case: the hot-emission
# parameters of the EMEP/EEA Guidebook's road transport Appendix 4 (July 2026,
# COPERT 5.10) for a scenario fleet, since MASS-GT's Dutch data say nothing of
# Euro standards.
#
#   copert_vehicles.csv        MASS-GT's vehicle types as COPERT segments:
#                              diesel Euro VI D/E (DPF+SCR) trucks by carrying
#                              capacity, diesel N1-III Euro 6 d/e vans
#   copert_v_coefficients.csv  their parameters per pollutant, slope and load
#                              bin, reduction factors as fractions; CO2 from
#                              energy consumption at 74.1 g/MJ (IPCC 2006,
#                              diesel), exact as the speed function is linear
#                              in its numerator
# The declared comparison covers CO, NOx, PM exhaust and derived CO2 only.
# Energy consumption (EC) is not itself a mass pollutant.
#   non_exhaust_factors.csv    empty: the appendix has none

import sys
import os
from pathlib import Path

import pandas as pd

OUT = sys.argv[1]
SOURCE = f'{OUT}/sources/1.A.3.b.i-iv Road Transport Appendix 4 Emission Factors July 2026.xlsx'
TRUCK = ('Heavy Duty Trucks', 'Diesel', 'Euro VI D/E', 'DPF+SCR')
VAN = ('Light Commercial Vehicles', 'Diesel', 'Euro 6 d/e', 'DPF+SCR')
SEGMENTS = {
    'truck_small': (TRUCK, 'Rigid 7,5 - 12 t'), 'truck_medium': (TRUCK, 'Rigid 26 - 28 t'),
    'truck_large': (TRUCK, 'Rigid >32 t'), 'truck_trailer_small': (TRUCK, 'Articulated 14 - 20 t'),
    'truck_trailer_large': (TRUCK, 'Articulated 34 - 40 t'), 'tractor_trailer': (TRUCK, 'Articulated 40 - 50 t'),
    'special_vehicle': (TRUCK, 'Rigid 28 - 32 t'), 'van': (VAN, 'N1-III'),
}
POLLUTANTS = {'NOx': 'nox', 'PM Exhaust': 'pm', 'CO': 'co', 'EC': '_energy'}
CO2_PER_MJ = 74.1
GRADES, LOADS = (-6, -4, -2, 0, 2, 4, 6), (0, 50, 100)

hot = pd.read_excel(SOURCE, sheet_name='HOT_EMISSIONS_PARAMETERS')
hot.columns = [' '.join(str(c).split()) for c in hot.columns]
rows, vehicles = [], []
for vehicle, ((category, fuel, euro, technology), segment) in SEGMENTS.items():
    label = f'{category} {segment} {fuel} {euro}'
    vehicles.append((vehicle, label))
    part = hot[(hot['Category'] == category) & (hot['Fuel'] == fuel) & (hot['Euro Standard'] == euro)
               & (hot['Technology'] == technology) & (hot['Segment'] == segment) & hot['Mode'].isna()]
    assert len(part), label
    for _, r in part.iterrows():
        if r['Pollutant'] not in POLLUTANTS:
            continue
        # A row without slope or load holds for every bin.
        grades = GRADES if pd.isna(r['Road Slope']) else (round(r['Road Slope'] * 100),)
        loads = LOADS if pd.isna(r['Load']) else (round(r['Load'] * 100),)
        coefficients = [r[name] for name in ('Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon', 'Zita', 'Hta')]
        for grade in grades:
            for load in loads:
                base = (label, grade, load, *coefficients, r['Reduction Factor [%]'] / 100, r['Min Speed [km/h]'], r['Max Speed [km/h]'])
                if r['Pollutant'] != 'EC': rows.append((POLLUTANTS[r['Pollutant']],) + base)
                if r['Pollutant'] == 'EC':
                    scaled = [c * CO2_PER_MJ for c in coefficients[:4]] + coefficients[4:]
                    rows.append(('co2', label, grade, load, *scaled, *base[-3:]))
columns = ['pollutant', 'vehicle_type', 'gradient_bin', 'payload_bin', 'alpha', 'beta', 'gamma', 'delta', 'epsilon',
           'zeta', 'eta', 'rf', 'min_speed', 'max_speed']
table = pd.DataFrame(rows, columns=columns).drop_duplicates(['vehicle_type', 'pollutant', 'gradient_bin', 'payload_bin'])
table[columns[1:2] + columns[:1] + columns[2:]].to_csv(f'{OUT}/copert_v_coefficients.csv', index=False)
pd.DataFrame(vehicles, columns=['vehicle', 'vehicle_type']).to_csv(f'{OUT}/copert_vehicles.csv', index=False)
pd.DataFrame(columns=['vehicle_type', 'pollutant', 'emission_factor']).to_csv(f'{OUT}/non_exhaust_factors.csv', index=False)
print('vehicle types', len(vehicles), '| coefficient rows', len(table), '| pollutants', sorted(table['pollutant'].unique()))
