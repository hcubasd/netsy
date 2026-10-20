"""General output indicators: totals and arbitrary case-defined groupings.

This is the reporting boundary corresponding to MASS-GT's OUTP, without
Dutch municipal names, sector codes or a fixed presentation format.
"""
import numpy as np
import pandas as pd

IDENTITIES={'link_id','time_interval','vehicle','segment','combustion','payload_bin'}


def indicators(name, table, groups=None, lengths=None):
    metrics={}
    if name=='agents': metrics={'actors':(np.ones(len(table)),'count'),'size':(table['size'].to_numpy(float),'size_units')}
    elif name in ('shipments','flows'): metrics={('od_pairs' if name=='flows' else 'consignments'):(np.ones(len(table)),'count'),'quantity':(table.quantity.to_numpy(float),'quantity_units')}
    elif name in ('tours','deliveries'):
        metrics={'trips':(np.ones(len(table)),'count')}
        if 'parcels' in table:
            metrics['parcel_legs']=(table.parcels.to_numpy(float),'parcels')
            final=table.final_delivery if 'final_delivery' in table else np.ones(len(table),bool)
            metrics['customer_parcels']=(table.parcels.to_numpy(float)*np.asarray(final,dtype=bool),'parcels')
        if 'quantity' in table: metrics['empty_trips']=((table.quantity.to_numpy(float)==0).astype(float),'count')
    elif name=='loads':
        if lengths is None: raise ValueError('network lengths are required for load indicators')
        distance=table.link_id.astype(str).map(lengths)
        if distance.isna().any():raise ValueError('every loaded link needs a network length')
        metrics={'link_traversals':(table.trips.to_numpy(float),'count'),'vehicle_km':(table.trips.to_numpy(float)*distance.to_numpy(float),'vehicle_km')}
    elif name=='emissions': metrics={c:(table[c].to_numpy(float),'grams') for c in table if c not in IDENTITIES}
    else: raise ValueError(f'unknown indicator table {name!r}')
    columns=[''] if groups is None else groups
    output=[]
    for column in columns:
        if column and column not in table:raise ValueError(f'{name}: unknown indicator grouping {column!r}')
        keys=table[column].fillna('(empty)').astype(str) if column else pd.Series('all',index=table.index)
        for metric,(values,unit) in metrics.items():
            totals=pd.Series(values,index=table.index).groupby(keys,sort=True).sum()
            output.extend((name,column or 'all',key,metric,float(value),unit) for key,value in totals.items())
        if name in ('tours','deliveries'):
            totals=table.groupby(keys,sort=True).tour_id.nunique()
            output.extend((name,column or 'all',key,'tours',float(value),'count') for key,value in totals.items())
    return pd.DataFrame(output,columns=['table','group','group_value','indicator','value','unit'])
