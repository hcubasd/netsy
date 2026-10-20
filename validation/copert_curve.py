"""Export the plotted coefficient sensitivity, with explicit units and assumptions."""
from pathlib import Path
import numpy as np
import pandas as pd
from netsy.synth.network_emissions import _hot_emission_factor
c=pd.read_csv('/workdir/netherlands/copert_v_coefficients.csv');v=pd.read_csv('/workdir/netherlands/copert_vehicles.csv');kind=v.loc[v.vehicle=='truck_medium','vehicle_type'].iloc[0]
legacy=pd.read_csv('/workdir/netherlands/emission_factors.csv');r=legacy[(legacy.vehicle=='truck_medium')&(legacy.road_type=='GOW_bibeko_50')&(legacy.pollutant=='nox')].iloc[0]
rows=[]
for grade in [-4,0,4]:
 coefficient=c[(c.vehicle_type==kind)&(c.pollutant=='nox')&(c.gradient_bin==grade)&(c.payload_bin==50)].iloc[0]
 speeds=np.linspace(10,80,200);factors=_hot_emission_factor(coefficient.to_dict(),np.clip(speeds,coefficient.min_speed,coefficient.max_speed))
 rows.extend((speed,grade,50,float(factor),float((r['empty']+r['full'])/2)) for speed,factor in zip(speeds,factors))
pd.DataFrame(rows,columns=['speed_kmh','grade_percent','payload_percent','copert_nox_g_km','legacy_nox_g_km']).to_csv(Path(__file__).parent/'results/copert_curve.csv',index=False)
