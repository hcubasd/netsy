import sys
import numpy as np
from netsy.cli._output import may_write
from netsy.helpers.files import read_facilities, read_table, read_zones
from netsy.helpers.skims import read_skims
from netsy.synth.parcel_routing import parcel_routing


def run(force=False, seed=None):
    output='routed_parcel_demand.csv'
    if not may_write(output,force): return 1
    try:
        result=parcel_routing(read_table('parcel_demand.csv'),read_zones('zones.gpkg'),read_facilities('facilities.gpkg'),
            read_skims('skims.omx'),read_table('parcel_routing_settings.csv'),read_table('parcel_routing_vehicles.csv'),np.random.default_rng(seed))
    except ValueError as error:
        print(error,file=sys.stderr);return 1
    result.to_csv(output,index=False);return 0
