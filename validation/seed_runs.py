"""Three independent NetSy seeds for the stochastic baseline stages.
The MASS-GT reference is fixed: this is NetSy seed sensitivity, not a
confidence interval for the difference between two stochastic models.
"""
import subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
for seed in (1,2,3):
 case=Path(f'/workdir/netsy-validation/seed-{seed}')
 subprocess.run([sys.executable,str(root/'validation/prepare_case.py'),str(case)],check=True)
 subprocess.run([sys.executable,str(root/'validation/run_case.py'),str(case),'--full','--seed',str(seed)]+(['--assignment'] if seed==1 else []),check=True)
