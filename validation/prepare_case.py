"""Create an isolated run directory; inputs link to a built case, outputs never do."""
import argparse
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--base',type=Path,default=Path('/workdir/netherlands'));a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
outputs={'agents.gpkg','shipments.gpkg','routed_shipments.gpkg','routed_parcel_demand.csv','tours.gpkg','tour_shipments.csv','parcel_demand.csv','delivery_tours.gpkg','network_loads.parquet','network_emissions.parquet','trip_matrices.omx','timings.json'}
for f in a.base.resolve().iterdir():
 if f.is_file() and f.name not in outputs and f.suffix in ('.csv','.omx','.gpkg') and not (a.output/f.name).exists(): (a.output/f.name).symlink_to(f)
