"""Rebuild MASS-GT hourly freight matrices with consistent [0,24) time.
Does not change shipments, tours, assignment, or emissions algorithms.
"""
import argparse
from pathlib import Path
import pandas as pd
p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--label',default='UCC');a=p.parse_args()
t=pd.read_csv(a.run/f'Tours_{a.label}.csv');t['hour']=t.TRIP_DEPTIME.mod(24).astype(int)
columns=['ORIG','DEST']+[f'N_LS{i}' for i in range(8)]+[f'N_VEH{i}' for i in range(10)]+['N_TOT']
for h in range(24):
 s=t[t.hour==h].copy()
 for i in range(8): s[f'N_LS{i}']=(s.LS==i).astype(int)
 for i in range(10): s[f'N_VEH{i}']=(s.VEHTYPE==i).astype(int)
 s['N_TOT']=1
 out=s.groupby(['ORIG','DEST'])[columns[2:]].sum().reset_index()
 dest=a.run/f'tripmatrix_{a.label}_TOD{h}.txt'
 if not dest.with_suffix('.txt.original').exists(): dest.rename(dest.with_suffix('.txt.original'))
 out.to_csv(dest,index=False,sep='\t')
print(f'Rebuilt 24 matrices: {len(t)} trips; original matrices retained as .txt.original')
