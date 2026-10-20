"""Dutch UCC and illustrative microhub adapters; all Dutch semantics live here.
Usage: python validation/build_scenario.py ucc|microhub OUTPUT
Baseline must already have been built with /workdir/netherlands/run.sh.
"""
import argparse
from pathlib import Path
import shutil
import geopandas as gpd
import numpy as np
import pandas as pd

p=argparse.ArgumentParser();p.add_argument('scenario',choices=['ucc','microhub']);p.add_argument('output',type=Path);a=p.parse_args()
base=Path('/workdir/netherlands');source=Path('/workdir/sweden/mass-gt/data/NL_main');out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
# Input links keep one copy of the 356 MB skim. Output files must never link to the baseline.
outputs={'agents.gpkg','shipments.gpkg','tours.gpkg','tour_shipments.csv','parcel_demand.csv','delivery_tours.gpkg','network_loads.parquet','network_emissions.parquet','trip_matrices.omx'}
mutable={'zones.gpkg','facilities.gpkg','network.gpkg','road_costs.csv','assignment_vehicles.csv','shipment_vehicles.csv','matrix_assignment.csv','emission_factors.csv','copert_vehicles.csv','copert_v_coefficients.csv','link_speeds.csv'}
for name in mutable:
 target=out/name
 if target.is_symlink(): target.unlink()
for f in base.iterdir():
 if not f.is_file() or f.name=='run.sh' or f.name in mutable: continue
 target=out/f.name
 if target.exists(): continue
 if f.name in outputs:
  if f.name in ('shipments.gpkg','parcel_demand.csv','trip_matrices.omx'): target.symlink_to(f)
 else: target.symlink_to(f)
zones=gpd.read_file(base/'zones.gpkg');original=gpd.read_file(source/'data/Zones_v6.shp').set_index('AREANR')
for dest,src in [('policy_zone','ZEZ'),('policy_area','GEMEENTEN')]: zones[dest]=zones.zone_id.map(original[src]).fillna(0)
zones['routing_facility']=zones.zone_id.map(original.UCC_zone).fillna(0).map(lambda z:f'ucc_{int(z)}' if z else None)
facilities=gpd.read_file(base/'facilities.gpkg')
ucczones=sorted(set(original.UCC_zone)-{0});points=zones.set_index('zone_id').geometry.centroid
added=gpd.GeoDataFrame([{'facility_id':f'ucc_{int(z)}','facility_type':'ucc','zone_id':int(z),'size':1,'operator':'collaborative','geometry':points.loc[int(z)]} for z in ucczones],crs=zones.crs)
facilities=pd.concat([facilities,added],ignore_index=True)
network=gpd.read_file(base/'network.gpkg');links=gpd.read_file(source/'data/links_v5.shp',ignore_geometry=True)
# TRAF derives ZEZ at link midpoints if it was absent in the input. Reference output is authoritative for that preprocessing.
ref=pd.read_csv('/workdir/sweden/mass-gt/runs/NL_REF/links_loaded_REF_intensities.csv')
network['policy_zone']=ref.ZEZ.to_numpy() if 'ZEZ' in ref else links.get('ZEZ',pd.Series(0,index=links.index)).to_numpy()
network['policy_zone']=(pd.to_numeric(network.policy_zone)>0).astype(int)
network.to_file(out/'network.gpkg',driver='GPKG')
VEHICLES=['truck_small','truck_medium','truck_large','truck_trailer_small','truck_trailer_large','tractor_trailer','special_vehicle','van','levv','moped']
SEGMENTS=['food','miscellaneous','temperature_controlled','facility','construction','waste','parcel_consolidated','dangerous']
COMBUSTIONS=['fuel','electric','hydrogen','hybrid','biofuel']
shares=pd.read_csv(source/'data/ZEZscenario.txt',sep='\t')
# Correct repeated vehicle shares: one vehicle probability, not once per combustion alternative.
vehicles=shares.drop_duplicates(['logistic_segment','vehicle_type'])
vehicles=pd.DataFrame({'segment':vehicles.logistic_segment.map(dict(enumerate(SEGMENTS))), 'vehicle':vehicles.vehicle_type.map(dict(enumerate(VEHICLES))), 'share':vehicles.share_vehicle})
vehicles.to_csv(out/'routing_vehicles.csv',index=False)
prob=pd.read_csv(source/'data/ConsolidationPotential.txt',sep='\t');prob.logistic_segment=prob.logistic_segment.map(dict(enumerate(SEGMENTS)))
prob.rename(columns={'logistic_segment':'segment'}).to_csv(out/'routing_probabilities.csv',index=False)
pd.DataFrame([('zone_column','policy_zone'),('facility_column','routing_facility'),('area_column','policy_area')],columns=['setting','value']).to_csv(out/'routing_settings.csv',index=False)
comb=[]
for _,r in shares.iterrows():
 for carrier,relation in [('ucc',None),('independent','all'),('distribution_centre','all'),('transshipment_terminal','all')]:
  comb.append((carrier,relation,SEGMENTS[int(r.logistic_segment)],VEHICLES[int(r.vehicle_type)],COMBUSTIONS[int(r.combustion_type)],r.share_combustion))
# Missing distributions have an explicit fuel fallback, correcting upstream's uniform draw.
for carrier in ['ucc','independent','distribution_centre','transshipment_terminal','parcel_depot']:
 for relation in ['all','some','none']:
  comb.append((carrier,relation,None,None,'hybrid' if relation=='some' else 'fuel',1))
# Specific distributions above must beat fallback keys (segment+vehicle specificity).
pd.DataFrame(comb,columns=['carrier_type','zone_relation','segment','vehicle','combustion','share']).to_csv(out/'combustion_shares.csv',index=False)
pd.DataFrame([('zone_column','policy_zone')],columns=['setting','value']).to_csv(out/'combustion_settings.csv',index=False)
assignment=pd.read_csv(base/'assignment_vehicles.csv')
assignment=pd.concat([assignment,pd.DataFrame([('levv','van',28.9275,.163989),('moped','van',28.9275,.163989)],columns=assignment.columns)],ignore_index=True)
assignment.to_csv(out/'assignment_vehicles.csv',index=False)
costs=pd.read_csv(base/'road_costs.csv');penalties=[]
for combustion in ['fuel','electric','hydrogen','biofuel']:
 penalties.append(('*',None,10000,combustion,'policy_zone',1,'add'))
policy=pd.DataFrame(penalties,columns=['road_type','speed_class','cost','combustion','attribute','value','operation'])
pd.concat([costs,policy],ignore_index=True).to_csv(out/'road_costs.csv',index=False)
# Exhaust multipliers, independent of non-exhaust. Hybrids emit outside the flagged links.
rules=[(c,'exhaust',None,0) for c in ['electric','hydrogen']]+[('hybrid','exhaust',1,0)]
pd.DataFrame(rules,columns=['combustion','source','policy_zone','multiplier']).to_csv(out/'emission_multipliers.csv',index=False)
settings=[('flag_column','policy_zone'),('flag_min',1),('facility_type','ucc'),('probability',float(prob.loc[prob.logistic_segment=='parcel_consolidated','probability'].iloc[0])),('selection','minimum_detour'),('area_column','policy_area')]
# Parcel UCC model explicitly has van and LEVV alternatives (not all freight vehicles).
parcelshares=pd.DataFrame([('van',.5),('levv',.5)],columns=['vehicle','share'])
if a.scenario=='microhub':
 raw=pd.read_csv('/workdir/sweden/mass-gt/data/NL_2023fmt/data/Microhubs.csv')
 print('Microhub source columns:',raw.columns.tolist())
 # This case is an explicit illustrative collaborative layout, not a claim that an upstream MIC configuration ran.
 if 'AREANR' not in raw: raise ValueError('microhub source needs AREANR')
 modes=pd.read_csv('/workdir/sweden/mass-gt/data/NL_2023fmt/data/Microhubs_vehicleTypes.csv')
 mode=modes[modes.Tag=='EB'].iloc[0]
 selected={int(i) for i in mode.collab_microhubs.split(',')}
 raw=raw[raw.ID.isin(selected) & raw.AREANR.isin(zones.zone_id)]
 hubs=gpd.GeoDataFrame([{'facility_id':f'microhub_{i}','facility_type':'microhub','zone_id':int(r.AREANR),'size':1,'operator':r.get('CEP','collaborative'),'geometry':points.loc[int(r.AREANR)]} for i,r in raw.iterrows()],crs=zones.crs)
 facilities=pd.concat([facilities,hubs],ignore_index=True)
 settings=[('flag_column','policy_zone'),('flag_min',2),('facility_type','microhub'),('probability',1),('selection','nearest'),('inbound_vehicle','parcel_truck')]
 parcelshares=pd.DataFrame([('electric_bicycle',1)],columns=['vehicle','share'])
 assignment=pd.concat([assignment,pd.DataFrame([('electric_bicycle','bicycle',0,0.1),('parcel_truck','freight',43.52,.322)],columns=assignment.columns)],ignore_index=True)
 assignment.to_csv(out/'assignment_vehicles.csv',index=False)
 # No UCC road penalties for the independent MIC experiment.
 costs=pd.concat([costs,pd.DataFrame([('Autosnelweg','bicycle',0,'exclude'),('Autoweg','bicycle',0,'exclude')],columns=['road_type','speed_class','cost','operation'])],ignore_index=True)
 costs.to_csv(out/'road_costs.csv',index=False)
zones.to_file(out/'zones.gpkg',driver='GPKG');facilities.to_file(out/'facilities.gpkg',driver='GPKG')
settings.append(('pool_operators',1))
pd.DataFrame(settings,columns=['setting','value']).to_csv(out/'parcel_routing_settings.csv',index=False)
parcelshares.to_csv(out/'parcel_routing_vehicles.csv',index=False)
delivery_rows=[('van',180,2/60,1,.5),('levv',36,2/60,1,.5),('moped',20,2/60,1,.5)]
if a.scenario=='microhub': delivery_rows.extend([('electric_bicycle',int(mode.Capacity),2/60,float(mode.AvgSpeed)/18,.5),('parcel_truck',1800,0,1,.5)])
delivery_parameters=pd.DataFrame(delivery_rows,columns=['vehicle','max_load','drop_time','speed_multiplier','utilization'])
if a.scenario=='microhub': delivery_parameters.loc[delivery_parameters.vehicle=='electric_bicycle','speed_kmh']=float(mode.AvgSpeed)
delivery_parameters.to_csv(out/'delivery_vehicles.csv',index=False)
print(a.scenario,out,'zones',len(zones),'facilities',len(facilities))

# Delivery powertrain rules: UCC/microhub tours electric; other tours touching restricted zones hybrid.
rules=[(kind,None,'electric',1) for kind in ['ucc','microhub']]
for kind in ['parcel_depot']:
 for relation in ['all','some','none']:
  rules.append((kind,relation,'hybrid' if a.scenario=='ucc' and relation!='none' else 'fuel',1))
pd.DataFrame(rules,columns=['carrier_type','zone_relation','combustion','share']).to_csv(out/'delivery_combustion_shares.csv',index=False)

shipment_vehicles=pd.read_csv(base/'shipment_vehicles.csv')
shipment_vehicles=pd.concat([shipment_vehicles,pd.DataFrame([('van',1.5,28.9275,.163989),('levv',1,28.9275,.163989),('moped',.1,28.9275,.163989)],columns=shipment_vehicles.columns)],ignore_index=True)
path=out/'shipment_vehicles.csv'
if path.is_symlink(): path.unlink()
shipment_vehicles.to_csv(path,index=False)

matrix_assignment=pd.read_csv(base/'matrix_assignment.csv')
if a.scenario=='ucc':
 matrix_assignment['combustion_zone_column']='policy_zone'
 matrix_assignment['flagged_combustion']='hybrid'
path=out/'matrix_assignment.csv'
if path.is_symlink(): path.unlink()
matrix_assignment.to_csv(path,index=False)

if a.scenario=='microhub':
 for name in ['tours.gpkg','tour_shipments.csv']:
  if not (out/name).exists(): (out/name).symlink_to(base/name)

# The new inbound truck uses the supplied medium-truck factors; zero-tailpipe cycling is explicit.
factors=pd.read_csv(base/'emission_factors.csv')
if a.scenario=='microhub':
 extra=factors[factors.vehicle=='truck_medium'].copy();extra['vehicle']='parcel_truck'
 factors=pd.concat([factors,extra],ignore_index=True)
factors.to_csv(out/'emission_factors.csv',index=False)
cv=pd.read_csv(base/'copert_vehicles.csv');coeff=pd.read_csv(base/'copert_v_coefficients.csv')
if a.scenario=='microhub':
 truck_type=cv.loc[cv.vehicle=='truck_medium','vehicle_type'].iloc[0]
 cv=pd.concat([cv,pd.DataFrame([('parcel_truck',truck_type),('electric_bicycle','zero_tailpipe')],columns=cv.columns)],ignore_index=True)
 zero=coeff.copy();zero['vehicle_type']='zero_tailpipe';zero=zero.drop_duplicates(['vehicle_type','pollutant','gradient_bin','payload_bin'])
 for c in ['alpha','beta','gamma','delta','epsilon','zeta','rf']: zero[c]=0
 zero['eta']=1;coeff=pd.concat([coeff,zero],ignore_index=True)
# Additional small UCC vehicle types use explicit zero tailpipe mappings in this electric scenario.
for v in ['levv','moped']:
 if v not in set(cv.vehicle):
  ref_type=cv.loc[cv.vehicle=='van','vehicle_type'].iloc[0]
  cv=pd.concat([cv,pd.DataFrame([(v,ref_type)],columns=cv.columns)],ignore_index=True)
cv.to_csv(out/'copert_vehicles.csv',index=False);coeff.to_csv(out/'copert_v_coefficients.csv',index=False)

speeds=pd.read_csv(base/'link_speeds.csv')
if a.scenario=='microhub':
 bicycle=speeds[speeds.speed_class=='van'].copy();bicycle['speed_class']='bicycle';bicycle['speed']=bicycle.speed.clip(upper=float(mode.AvgSpeed))
 speeds=pd.concat([speeds,bicycle],ignore_index=True)
speeds.to_csv(out/'link_speeds.csv',index=False)
