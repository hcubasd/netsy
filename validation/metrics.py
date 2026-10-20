"""Compute side-by-side Dutch stage metrics from artifacts, never prose claims."""
from pathlib import Path
import json
import geopandas as gpd
import numpy as np
import pandas as pd
from netsy.helpers.skims import read_skims,read_matrices
from netsy.synth.shipments import _intrazonal
BASE=Path('/workdir/netherlands');REF=Path('/workdir/sweden/mass-gt/runs/NL_REF');OUT=Path(__file__).parent/'results';OUT.mkdir(exist_ok=True)
RESOURCES=['agricultural_products','foodstuffs','solid_mineral_fuels','petroleum_products','ores_and_metal_waste','metal_products','minerals_and_building_materials','fertilizers','chemicals','machinery_and_manufactured_articles']
SEGMENTS=['food','miscellaneous','temperature_controlled','facility','construction','waste','parcel_consolidated','dangerous','parcel_deliveries']
VEHICLES=['truck_small','truck_medium','truck_large','truck_trailer_small','truck_trailer_large','tractor_trailer','special_vehicle','van','levv','moped']
ids,T,D=read_skims(str(BASE/'skims.omx'));D=_intrazonal(D);ix={str(z):i for i,z in enumerate(ids)}
def km(o,d):return D[np.array([ix[str(int(z))] for z in o]),np.array([ix[str(int(z))] for z in d])]
def tour_metrics(t,reference=False):
 if reference:
  tours=t.CARRIER_ID.astype(str)+'_'+t.TOUR_ID.astype(str);distance=km(t.ORIG,t.DEST);load=t.TRIP_WEIGHT
 else:tours=t.tour_id;distance=km(t.origin_zone_id,t.destination_zone_id);load=t.quantity
 return {'tours':int(tours.nunique()),'trips':len(t),'vkt':float(distance.sum(dtype=np.float64)),'tonne_km':float((distance*load).sum()),'empty_vkt':float(distance[np.asarray(load)==0].sum(dtype=np.float64))}
def parcel_metrics(t,reference=False):
 if reference:distance=km(t.O_zone,t.D_zone);tour=t.Tour_ID;parcels=t.N_parcels
 else:distance=km(t.origin_zone_id,t.destination_zone_id);tour=t.tour_id;parcels=t.parcels
 result={'tours':int(tour.nunique()),'trips':len(t),'vkt':float(distance.sum(dtype=np.float64)),'leg_parcels':int(parcels.sum())}
 if not reference and 'final_delivery' in t:result['customer_parcels']=int(parcels[t.final_delivery].sum())
 return result
def own(case):
 result={}
 for file,key in [('agents.gpkg','agents'),('shipments.gpkg','shipments')]:
  if not (case/file).exists():continue
  t=gpd.read_file(case/file,ignore_geometry=True)
  result[key]={'count':len(t),'size':float(t['size'].sum())} if key=='agents' else {'count':len(t),'tonnes':float(t.quantity.sum()),'mean_tonnes':float(t.quantity.mean()),'vehicle_shares':t.vehicle.value_counts(normalize=True).to_dict()}
 for file,key,func in [('tours.gpkg','tours',tour_metrics),('delivery_tours.gpkg','deliveries',parcel_metrics)]:
  if (case/file).exists():result[key]=func(gpd.read_file(case/file,ignore_geometry=True))
 if (case/'parcel_demand.csv').exists():result['parcel_demand']=int(pd.read_csv(case/'parcel_demand.csv').parcels.sum())
 if (case/'routed_shipments.gpkg').exists():
  r=gpd.read_file(case/'routed_shipments.gpkg',ignore_geometry=True);result['routing']={'legs':len(r),'consignments':int(r.parent_transaction_id.nunique()),'routed_consignments':int(r.loc[r.routed==True,'parent_transaction_id'].nunique()),'leg_tonnes':float(r.quantity.sum())}
 if (case/'network_loads.parquet').exists():
  loads=pd.read_parquet(case/'network_loads.parquet');length=gpd.read_file(case/'network.gpkg',ignore_geometry=True).set_index('link_id').length
  distance=loads.link_id.astype(str).map(dict(zip(length.index.astype(str),length)))
  result['loads']={'rows':len(loads),'link_trips':float(loads.trips.sum()),'vkt':float((loads.trips*distance).sum())}
 if (case/'network_emissions.parquet').exists():
  emissions=pd.read_parquet(case/'network_emissions.parquet');result['emissions_grams']={c:float(emissions[c].to_numpy(dtype=float).sum()) for c in emissions if c not in ['link_id','time_interval','vehicle','segment','combustion','payload_bin']}
 return result
ref={};f=pd.read_csv(REF/'Firms.csv');ref['agents']={'count':len(f),'size':float(f.employment.sum())};s=pd.read_csv(REF/'Shipments_REF.csv');ref['shipments']={'count':len(s),'tonnes':float(s.WEIGHT.sum()),'mean_tonnes':float(s.WEIGHT.mean()),'vehicle_shares':s.VEHTYPE.map(dict(enumerate(VEHICLES))).value_counts(normalize=True).to_dict()}
ref['tours']=tour_metrics(pd.read_csv(REF/'Tours_REF.csv'),True);ref['deliveries']=parcel_metrics(pd.read_csv(REF/'ParcelSchedule_REF.csv'),True)
parcel=pd.read_csv(REF/'ParcelDemand_REF.csv');ref['parcel_demand']=int(parcel.Parcels.sum()) if 'Parcels' in parcel else len(parcel)
# SIF comparison after identical key normalization.
r=pd.read_csv(REF/'CommodityMatrixNUTS3.csv');r['resource']=r.NSTR.map(dict(enumerate(RESOURCES)))
o=pd.read_csv(BASE/'od_flows.csv');merged=o.merge(r,left_on=['resource','origin_location_id','destination_location_id'],right_on=['resource','ORIG','DEST'],how='outer')
ref['sif']={'pairs':len(merged),'max_abs_tonnes_year':float((merged.quantity-merged.TonnesYear).abs().max()),'max_abs_after_rounding':float((merged.quantity.round(3)-merged.TonnesYear).abs().max())}
# Reference assignment totals, as written. Emissions in kg, converted to grams.
l=pd.read_csv(REF/'links_loaded_REF_intensities.csv');ref['loads']={'link_trips':float(l.N_TOT.sum()),'vkt':float((l.N_TOT*l.LENGTH).sum())};ref['emissions_grams']={c.lower():float(l[c].sum()*1000) for c in ['CO2','SO2','PM','NOX']}
results={'massgt_reference':ref,'netsy_saved_baseline':own(BASE),'seeds':{}}
for seed in (1,2,3):
 case=Path(f'/workdir/netsy-validation/seed-{seed}')
 if case.exists(): results['seeds'][str(seed)]=own(case)
for key,name in [('ucc','netherlands-ucc'),('microhub','netherlands-microhub')]:
 case=Path('/workdir')/name
 if case.exists():results[key]=own(case)
ucc=Path('/workdir/sweden/mass-gt/runs/NL_UCC')
results['massgt_ucc']={'tours':tour_metrics(pd.read_csv(ucc/'Tours_UCC.csv'),True),'deliveries':parcel_metrics(pd.read_csv(ucc/'ParcelSchedule_UCC.csv'),True)}
if (ucc/'links_loaded_UCC_intensities.csv').exists():
 l=pd.read_csv(ucc/'links_loaded_UCC_intensities.csv');results['massgt_ucc']['loads']={'link_trips':float(l.N_TOT.sum()),'vkt':float((l.N_TOT*l.LENGTH).sum())};results['massgt_ucc']['emissions_grams']={c.lower():float(l[c].sum()*1000) for c in ['CO2','SO2','PM','NOX']}
results['contributions']={}
for name in ['savings','copert']:
 case=Path('/workdir/netsy-validation')/name
 if case.exists():results['contributions'][name]=own(case)
(OUT/'metrics.json').write_text(json.dumps(results,indent=2,allow_nan=False));print(json.dumps(results,indent=2))
