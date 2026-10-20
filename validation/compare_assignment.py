"""Controlled assignment: MASS-GT trips in both models, isolating routing and factors."""
from pathlib import Path
import json
import geopandas as gpd
import numpy as np
import pandas as pd
case=Path('/workdir/netsy-validation/reference-trips');ref=pd.read_csv('/workdir/sweden/mass-gt/runs/NL_REF/links_loaded_REF_intensities.csv')
loads=pd.read_parquet(case/'network_loads.parquet');emissions=pd.read_parquet(case/'network_emissions.parquet')
# Numeric row IDs refer to exactly the original network order.
ids=pd.Index([str(i) for i in range(1,len(ref)+1)])
bylink=loads.groupby(loads.link_id.astype(str)).trips.sum().reindex(ids,fill_value=0).to_numpy()
result={'source':'MASS-GT NL_REF tours, parcel schedule and original service matrices','links':len(ids),'max_abs_link_trips':float(np.abs(bylink-ref.N_TOT).max()),'sum_link_trip_difference':float(bylink.sum()-ref.N_TOT.sum()),'emissions':{}}
network=gpd.read_file(case/'network.gpkg',ignore_geometry=True);network['link_id']=network.link_id.astype(str)
parcels=loads[loads.segment=='parcel_deliveries'].copy();parcels['link_id']=parcels.link_id.astype(str);parcels=parcels.merge(network[['link_id','road_type','length']],on='link_id')
factors=pd.read_csv(case/'emission_factors.csv')
# The source overwrites city parcel emissions once per trip instead of adding them.
urban={'ETW_bibeko_30','GOW_bibeko_50','GOW_bibeko_70','WOW_bibeko_50','Verblijfsgebied_15'}
for pollutant,source in [('co2','CO2'),('so2','SO2'),('pm','PM'),('nox','NOX')]:
 ours=float(emissions[pollutant].to_numpy(dtype=float).sum());original=float(ref[source].sum()*1000)
 rates=factors[factors.pollutant==pollutant]
 rows=parcels.merge(rates,on=['vehicle','road_type'],how='left')
 factor=rows['empty']+rows.utilization*(rows.full-rows['empty'])
 correction=float(((rows.trips-1)*rows.length*factor).where(rows.road_type.isin(urban),0).sum())
 result['emissions'][pollutant]={'massgt_grams':original,'netsy_grams':ours,'difference_grams':ours-original,'predicted_urban_parcel_fix_grams':correction,'residual_grams':ours-original-correction}
Path('validation/results/assignment_control.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
