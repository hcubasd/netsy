import sys
import geopandas
import numpy as np
from netsy.cli._output import may_write
from netsy.helpers.files import read_zones, read_facilities, read_shipments, read_table
from netsy.synth.facility_routing import facility_routing


def run(force=False, seed=None):
    output = 'routed_shipments.gpkg'
    if not may_write(output, force):
        return 1
    try:
        result = facility_routing(read_shipments('shipments.gpkg'), read_zones('zones.gpkg'),
            read_facilities('facilities.gpkg'), read_table('routing_settings.csv'),
            read_table('routing_probabilities.csv'), read_table('routing_vehicles.csv'), np.random.default_rng(seed))
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    result.to_file(output, driver='GPKG')
    return 0
