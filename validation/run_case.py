"""Run an existing case with stage timings and logged, reproducible commands."""
import argparse, json, os, subprocess, sys, time, fcntl
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('case',type=Path);p.add_argument('--scenario',choices=['reference','ucc','microhub'],default='reference');p.add_argument('--seed',type=int,default=1);p.add_argument('--assignment',action='store_true');p.add_argument('--full',action='store_true');p.add_argument('--only',nargs='+');p.add_argument('--payload-strata',action='store_true');p.add_argument('--method',choices=['factors','copert'],default='factors');a=p.parse_args()
root=Path(__file__).resolve().parents[1];case=a.case.resolve();env=dict(os.environ,PYTHONPATH=str(root/'src'),NETSY_WORKERS='1');timings=[]
commands=[]
if a.full:
 commands += [('agents',['--min-size','4']),('shipments',[])]
if a.scenario=='ucc': commands += [('facility-routing',[]),('tours',['--shipments','routed_shipments.gpkg'])]
elif a.scenario=='reference': commands += [('tours',[])]
if a.scenario!='reference': commands += [('parcel-routing',[]),('deliveries',['--demand','routed_parcel_demand.csv'])]
else: commands += [('parcel-demand',[]),('deliveries',[]),('trip-matrices',[])]
if a.assignment: commands += [('network-loads',[]),('network-emissions',[])]
if a.only:
 lookup=dict(commands)
 commands=[(stage,lookup.get(stage,[])) for stage in a.only]
if (case/'timings.json').exists(): timings=json.loads((case/'timings.json').read_text())
for stage,extra in commands:
 if stage=='network-loads' and a.payload_strata: extra=extra+['--payload-strata']
 if stage=='network-emissions': extra=extra+['--method',a.method]
 cmd=[sys.executable,'-c','from netsy.cli.main import main;raise SystemExit(main())','synth',stage,'--force']+extra
 if stage in ['agents','shipments','tours','facility-routing','parcel-routing','deliveries']:cmd+=['--seed',str(a.seed)]
 start=time.perf_counter()
 with (case/f'{stage}.log').open('w') as log:
  with open('/tmp/netsy-validation-assignment.lock','w') as lock:
   if stage=='network-loads': fcntl.flock(lock,fcntl.LOCK_EX)
   result=subprocess.run(cmd,cwd=case,env=env,stdout=log,stderr=subprocess.STDOUT)
 elapsed=time.perf_counter()-start
 timings.append(dict(stage=stage,seconds=elapsed,returncode=result.returncode,command=cmd))
 (case/'timings.json').write_text(json.dumps(timings,indent=2))
 print(stage,round(elapsed,2),result.returncode,flush=True)
 if result.returncode:print((case/f'{stage}.log').read_text());sys.exit(result.returncode)
