# Builds NetSy's assignment and emission inputs for the Netherlands case from
# MASS-GT's Dutch network and settings, as its traffic assignment (TRAF) reads
# them with the NL_REF settings (IMPEDANCE_SPEED_FREIGHT = V_FR_OS,
# IMPEDANCE_SPEED_VAN = V_PA_OS, one route per OD).
#
#   network.gpkg             MASS-GT's directed links, in its order
#   zones.gpkg               gains the network node each zone loads at
#   assignment_vehicles.csv  trucks route by the sourcing cost at freight
#                            speeds, vans by the van cost at van speeds
#   link_speeds.csv          the two speed columns (0 or less as 50 km/h)
#   road_costs.csv           connectors, and links closed to trucks, at 10 000
#   time_intervals.csv       the 24 hours
#   matrix_assignment.csv    van service and construction trips of at least 0.1
#   emission_factors.csv     TRAF's empty and full factors per road type

import sys
import os
from pathlib import Path

import geopandas as gpd
import pandas as pd

MASSGT = os.environ.get('MASSGT_INPUT', '/workdir/sweden/mass-gt/data/NL_main')
OUT = sys.argv[1]
TRUCKS = ['truck_small', 'truck_medium', 'truck_large', 'truck_trailer_small', 'truck_trailer_large',
          'tractor_trailer', 'special_vehicle']
VEHICLES = TRUCKS + ['van', 'levv', 'moped']
LARGE = 10000
# TRAF's road types for emissions; its list spells 'Verblijfsgebied_15', which
# no link has, so 'Verblijfgebied_15' links, like connectors, ferries and
# parking, emit nothing.
ROAD_CLASSES = {
    2: ['ETW_bibeko_30', 'GOW_bibeko_50', 'GOW_bibeko_70', 'WOW_bibeko_50', 'Verblijfsgebied_15'],
    0: ['ETW_bubeko_breed_60', 'ETW_bubeko_smal_60', 'GOW_bubeko_gemengd_80', 'GOW_bubeko_gesloten_80',
        'Industrieontsluitingsweg_50', 'Industriestraat_30'],
    1: ['Autosnelweg', 'Autoweg', 'Vrachtverbod'],
}
POLLUTANTS = {0: 'co2', 1: 'so2', 2: 'pm', 3: 'nox'}

links = gpd.read_file(f'{MASSGT}/data/links_v5.shp').set_crs('EPSG:28992', allow_override=True)
network = gpd.GeoDataFrame({
    'link_id': range(1, len(links) + 1), 'linknr': links['LINKNR'].astype(int),
    'from_node': links['A'].astype(int), 'to_node': links['B'].astype(int),
    'length': links['LENGTH'].astype(float), 'road_type': links['WEGTYPE'], 'name': links['NAME'],
}, geometry=links.geometry, crs='EPSG:28992')


nodes = gpd.read_file(f'{MASSGT}/data/nodes_v5.shp', ignore_geometry=True)
order = dict(zip(nodes.NODENR, range(len(nodes))))
network['from_node_order'] = network.from_node.map(order)
network['to_node_order'] = network.to_node.map(order)
network.to_file(f'{OUT}/network.gpkg', driver='GPKG')
zones = gpd.read_file(f'{OUT}/zones.gpkg')
centroids = nodes[nodes['TYPENO'] == 99].set_index('AREANR')['NODENR']
zones['node'] = [z + 10000000 if z < 99999900 else int(centroids[z]) for z in zones['zone_id']]
missing = set(zones['node']) - set(nodes['NODENR'])
assert not missing, missing
zones.to_file(f'{OUT}/zones.gpkg', driver='GPKG')

sourcing = pd.read_csv(f'{MASSGT}/parameters/Cost_Sourcing.txt', sep='\t').iloc[0]
van = pd.read_csv(f'{MASSGT}/parameters/Cost_VehType.txt', sep='\t').set_index('vehicle_type').loc[7]
pd.DataFrame(
    [(v, 'freight', sourcing['cost_per_hour'], sourcing['cost_per_km']) for v in TRUCKS]
    + [('van', 'van', van['cost_per_hour'], van['cost_per_km'])],
    columns=['vehicle', 'speed_class', 'cost_per_hour', 'cost_per_km'],
).to_csv(f'{OUT}/assignment_vehicles.csv', index=False)

speeds = pd.concat([
    pd.DataFrame({'link_id': network['link_id'], 'speed_class': name, 'speed': links[column].where(links[column] > 0, 50)})
    for name, column in (('freight', 'V_FR_OS'), ('van', 'V_PA_OS'))
])
speeds.to_csv(f'{OUT}/link_speeds.csv', index=False)
pd.DataFrame([('voedingslink', None, LARGE), ('Vrachtverbod', 'freight', LARGE), ('Vrachtstrook', 'freight', LARGE)],
             columns=['road_type', 'speed_class', 'cost']).to_csv(f'{OUT}/road_costs.csv', index=False)
pd.DataFrame({'time_interval': [str(h) for h in range(24)], 'start': range(24), 'end': range(1, 25)}).to_csv(
    f'{OUT}/time_intervals.csv', index=False)
pd.DataFrame([('service', 'van', 'van_service', 0.5, 0.1), ('construction', 'van', 'van_construction', 0.5, 0.1)],
             columns=['matrix', 'vehicle', 'segment', 'utilization', 'minimum']).to_csv(f'{OUT}/matrix_assignment.csv', index=False)

factors = pd.read_csv(f'{MASSGT}/data/EmissionFactors.txt', sep='\t')
factors = factors.pivot_table(index=['vehicle_type', 'road_type', 'emission_type'], columns='is_loaded',
                              values='factor_gram_per_km').reset_index()
rows = [
    (VEHICLES[int(r['vehicle_type'])], road_type, POLLUTANTS[int(r['emission_type'])], r[0], r[1])
    for _, r in factors.iterrows() for road_type in ROAD_CLASSES[int(r['road_type'])]
]
pd.DataFrame(rows, columns=['vehicle', 'road_type', 'pollutant', 'empty', 'full']).to_csv(f'{OUT}/emission_factors.csv', index=False)
print('links', len(network), '| zones with nodes', len(zones), '| factor rows', len(rows))
