import os,sys
import geopandas
import pandas as pd
from netsy.cli._output import may_write
from netsy.synth.indicators import indicators

SOURCES={'agents':'agents.gpkg','shipments':'shipments.gpkg','tours':'tours.gpkg','deliveries':'delivery_tours.gpkg',
         'loads':'network_loads.parquet','emissions':'network_emissions.parquet','flows':'od_flows.csv'}


def run(force=False):
    if not may_write('indicators.csv',force):return 1
    try:
        groups=pd.read_csv('indicator_groups.csv',keep_default_na=False) if os.path.exists('indicator_groups.csv') else None
        if groups is not None and not {'table','column'} <= set(groups): raise ValueError('indicator_groups.csv requires table and column')
        lengths=None
        if os.path.exists('network_loads.parquet'):
            network=geopandas.read_file('network.gpkg',ignore_geometry=True)
            lengths=dict(zip(network.link_id.astype(str),network.length))
        results=[]
        for name,path in SOURCES.items():
            if not os.path.exists(path):continue
            table=pd.read_parquet(path) if path.endswith('.parquet') else pd.read_csv(path) if path.endswith('.csv') else geopandas.read_file(path,ignore_geometry=True)
            selected=None if groups is None else groups.loc[groups.table==name,'column'].tolist()
            if selected==[]:continue
            results.append(indicators(name,table,selected,lengths))
            del table
        if os.path.exists('trip_matrices.omx'):
            from netsy.helpers.skims import read_matrices
            import numpy as np
            _, matrices=read_matrices('trip_matrices.omx')
            results.append(pd.DataFrame([('trip_matrices','matrix',name,'trips',float(matrix.sum(dtype=np.float64)),'count') for name,matrix in matrices.items()],columns=['table','group','group_value','indicator','value','unit']))
        if not results:raise ValueError('no model outputs found for indicators')
        pd.concat(results,ignore_index=True).to_csv('indicators.csv',index=False)
    except (ValueError,OSError) as error:
        print(error,file=sys.stderr);return 1
    return 0
