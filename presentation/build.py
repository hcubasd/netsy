"""Build slides' numbers and two explanatory plots from saved validation results."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'presentation';FIG=OUT/'figures';FIG.mkdir(exist_ok=True)
m=json.loads((ROOT/'validation/results/metrics.json').read_text());v=json.loads((ROOT/'validation/results/vans.json').read_text());a=json.loads((ROOT/'validation/results/assignment_control.json').read_text());mic=json.loads((ROOT/'validation/results/microhub_control.json').read_text());browser=json.loads((ROOT/'validation/results/browser.json').read_text())
r=m['massgt_reference'];seeds=list(m['seeds'].values());n=m['netsy_saved_baseline'];u=m['ucc'];ur=m['massgt_ucc'];micro=m['microhub'];saved=m['contributions']['savings'];cop=m['contributions']['copert']
macros=[]
def tex(s):return str(s).replace('_',r'\_').replace('%',r'\%').replace('&',r'\&')
def num(x,d=0):return f'{x:,.{d}f}'.replace(',',r'\,')
def command(name,body):macros.append("\\newcommand{\\"+name+"}{"+body+"}")
def table(headers,rows):
 return r'\centering\small\begin{tabular}{lrr}\toprule '+' & '.join(headers)+r'\\\midrule '+''.join(' & '.join(row)+r'\\ ' for row in rows)+r'\bottomrule\end{tabular}\par'
def band(stage,key,d=0):
 vals=[s[stage][key] for s in seeds];return num(min(vals),d) if round(min(vals),d)==round(max(vals),d) else num(min(vals),d)+'--'+num(max(vals),d)
command('SeedNote', 'NetSy seeds 1--3; one fixed MASS-GT reference. Ranges show seed sensitivity, not confidence intervals or a formal equivalence test.')
command('ActorTable',table(['Indicator','MASS-GT','NetSy'],[
 ['Actors retained',num(r['agents']['count']),band('agents','count')],
 ['Size retained (jobs)',num(r['agents']['size']),band('agents','size')],
 ['SIF: max. error after rounding',r'\multicolumn{2}{c}{'+num(r['sif']['max_abs_after_rounding'],3)+r' tonnes/year}'],
]))
command('FreightTable',table(['Indicator','MASS-GT','NetSy'],[
 ['Shipments',num(r['shipments']['count']),band('shipments','count')],
 ['Daily shipment tonnes',num(r['shipments']['tonnes'],2),band('shipments','tonnes',2)],
 ['Freight tours',num(r['tours']['tours']),band('tours','tours')],
 ['Freight VKT (million)',num(r['tours']['vkt']/1e6,3),num(min(s['tours']['vkt'] for s in seeds)/1e6,3)+'--'+num(max(s['tours']['vkt'] for s in seeds)/1e6,3)],
]))
command('ParcelVanTable',table(['Indicator','MASS-GT','NetSy'],[
 ['Customer parcels/day',num(r['parcel_demand']),num(n['parcel_demand'])],
 ['Service van trips/day',num(v['service']['massgt_trips'],1),num(v['service']['netsy_trips'],1)],
 ['Construction van trips/day',num(v['construction']['massgt_trips'],1),num(v['construction']['netsy_trips'],1)],
 ['Max. OD-cell difference', '--',num(max(d['max_abs_difference'] for d in v.values()),3)+' trips'],
]))
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
teal='#179299';gray='#8c8fa1';light='#9ca0b0'
fig,ax=plt.subplots(figsize=(6.0,3.5));values=[r['deliveries']['vkt'],n['deliveries']['vkt'],saved['deliveries']['vkt']]
bars=ax.bar(['MASS-GT\nreference','NetSy\nstop-index fix','NetSy\nsavings'],np.array(values)/1000,color=[gray,light,teal],width=.6)
for b,value in zip(bars,values):ax.text(b.get_x()+b.get_width()/2,b.get_height()+1.0,f'{value/1000:.1f}',ha='center')
ax.set_ylabel('Parcel vehicle-km / day (thousands)');ax.set_ylim(0,max(values)/1000*1.15);fig.tight_layout();fig.savefig(FIG/'parcels.pdf');plt.close(fig)
reduction=100*(1-saved['deliveries']['vkt']/n['deliveries']['vkt']);tour_change=100*(saved['deliveries']['tours']/n['deliveries']['tours']-1)
command('SavingsText',f'Savings vs. the corrected port: \\textbf{{{reduction:.1f}\\% less VKT}}, with {tour_change:+.1f}\\% tours. Same {num(r["parcel_demand"])} customer parcels.')
co=a['emissions']['co2'];command('AssignmentTable',table(['Indicator','MASS-GT','NetSy'],[
 ['Network links compared',r'\multicolumn{2}{c}{'+num(a['links'])+'}'],
 ['Max. connector trip error','--',num(a['max_abs_link_trips'],3)],
 ['Max. non-connector trip error','--',num(a['max_abs_non_connector_link_trips'],6)],
 ['CO$_2$ (tonnes/day)',num(co['massgt_grams']/1e6,3),num(co['netsy_grams']/1e6,3)],
 ['CO$_2$ change explained by fix',r'\multicolumn{2}{c}{'+num(co['predicted_urban_parcel_fix_grams']/1e6,3)+' tonnes/day}'],
]))
command('AssignmentNote',f'CO$_2$ residual after accounting for the fix: {num(abs(co["residual_grams"]),3)} g. Small load residuals occur on connectors (ties and the reference\'s eight-neighbour link lookup); see the audit.')
command('UccTable',table(['Indicator','MASS-GT UCC','NetSy UCC + pooling'],[
 ['Freight tours',num(ur['tours']['tours']),num(u['tours']['tours'])],
 ['Parcel tours',num(ur['deliveries']['tours']),num(u['deliveries']['tours'])],
 ['Customer parcels',num(r['parcel_demand']),num(u['deliveries']['customer_parcels'])],
 ['Network VKT (million)',num(ur['loads']['vkt']/1e6,3),num(u['loads']['vkt']/1e6,3)],
 ['CO$_2$ (tonnes/day)',num(ur['emissions_grams']['co2']/1e6,1),num(u['emissions_grams']['co2']/1e6,1)],
]))
command('UccNote','Independent stochastic runs, documented fixes and explicit outbound hub pooling; this is a scenario comparison, not an exact-match claim. Reference repaired only for execution/midnight handling; behavioural bugs are listed in the audit.')
f=mic['corrected_selection'];command('MicroTable',table(['Indicator','MASS-GT (corrected)','NetSy'],[
 ['Hub-bound customer parcels',num(f['massgt_hub_parcels']),num(f['netsy_hub_parcels'])],
 ['Max. hub--recipient pair error', '--',num(f['max_abs_hub_destination_parcels'])],
 ['Customer parcels delivered',r'\multicolumn{2}{c}{'+num(r['parcel_demand'])+'}'],
 ['Completed parcel tours','No hub-aware schedule',num(micro['deliveries']['tours'])],
]))
command('MicroNote','Collaborative electric-bicycle configuration from the supplied Dutch microhub tables. Raw-reference maximum hub-pair difference: 391 parcels; corrected difference: zero. Both references are retained; zero pair error is against corrected selection. NetSy adds the missing hub-aware downstream operations.')
# Published coefficient curves: declared Euro VI medium-truck scenario, not the paper's observed fleet.
curve=pd.read_csv(ROOT/'validation/results/copert_curve.csv')
curve=curve[curve.grade_percent==0]
speeds=curve.speed_kmh.to_numpy();fig,ax=plt.subplots(figsize=(6.0,3.5))
ax.plot(speeds,curve.copert_nox_g_km,label='COPERT: 0% grade',color=teal,lw=2)
ax.axhline(curve.legacy_nox_g_km.iloc[0],color='#4c4f69',ls='--',label='MASS-GT urban factor')
ax.set_yscale('log');ax.set_xlabel('Speed (km/h)');ax.set_ylabel('Hot-exhaust NOₓ (g/km, log scale)');ax.legend(frameon=False,fontsize=8);fig.tight_layout();fig.savefig(FIG/'copert.pdf');plt.close(fig)
copco=cop['emissions_grams']['co2'];command('CopertText',f'Full pipeline, same seed-1 trips:\\par factors: {num(m["seeds"]["1"]["emissions_grams"]["co2"]/1e6,1)} t CO$_2$;\\par COPERT: {num(copco/1e6,1)} t CO$_2$.\\par\\medskip A model/fleet sensitivity, not a measured emissions improvement.')
command('CopertNote','Declared Euro VI truck / Euro 6 van fleet; EMEP/EEA Appendix 4 (July 2026). Curve: medium truck, 0\\% grade, 50\\% payload. Dutch network run assumes flat grades; no non-exhaust estimate is claimed. Paper informs the speed/grade/payload and hub/powertrain extension.')
rows=browser['rowLabel'].split(', ')[1].split(' ')[0];elapsed=next(x['milliseconds'] for x in browser['timings'] if x['name'].endswith('.parquet'))/1000
command('BrowserText',f' The {num(int(rows))}-row loads file loaded in {elapsed:.1f} s in the recorded browser check.')
command('ValidationSummary','three NetSy seeds assess stochastic sensitivity, and original-trip controls isolate assignment/emissions.')
command('BoundaryNote','Scope: the standard Dutch pipeline, UCC and collaborative microhub case. Optional crowdshipping and selected-link analyses are not benchmarked here. Benchmark agreement is distinct from empirical validity of a new study case. Code, patches, inputs and comparison scripts are identified in validation/.')
(OUT/'results.tex').write_text('\n'.join(macros)+'\n')
print('Generated figures and slide data from saved validation results.')
