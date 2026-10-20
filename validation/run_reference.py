"""Execute the pinned MASS-GT checkout with disk-backed large zero arrays.
The numerical dtype, initial values, row order, and algorithms are unchanged.
Usage: reference_python run_reference.py CHECKOUT CONFIG
Use repair_reference_midnight.py before UCC assignment.
"""
import os, sys, tempfile, runpy, hashlib
from pathlib import Path
import numpy as np
checkout,config=Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve()
sys.path.insert(0,str(checkout/'src'))
_original_zeros=np.zeros
_files=[]
def disk_zeros(shape,dtype=float,order='C',**kwargs):
    n=int(np.prod(shape))*np.dtype(dtype).itemsize
    if n < 4_000_000 or kwargs:
        return _original_zeros(shape,dtype=dtype,order=order,**kwargs)
    f=tempfile.NamedTemporaryFile(prefix='massgt-',suffix='.array',dir=os.environ.get('MASSGT_ARRAY_DIR','/tmp'))
    _files.append(f)
    # Newly extended files are zero-filled by the OS; no eager page touching.
    f.truncate(n)
    return np.memmap(f.name,dtype=dtype,mode='r+',shape=shape,order=order)
np.zeros=disk_zeros
import tfs
# Cache the unmodified reference predecessor results and convert LIL to CSR once.
# SciPy otherwise repeats the same sparse conversion for every origin.
from calculation.traf import module_traf
_original_calc_prev = module_traf.calc_prev
_cache = checkout.parent / 'reference-route-cache'
_cache.mkdir(exist_ok=True)
def cached_calc_prev(graph, n_nodes, args):
    csr = graph.tocsr()
    digest = hashlib.sha256()
    for part in [csr.data, csr.indices, csr.indptr, np.asarray(args[0])]: digest.update(part.tobytes())
    name = _cache / (digest.hexdigest() + '.i32')
    shape = (len(args[0]), n_nodes)
    if name.with_suffix('.complete').exists():
        print('Reference route-cache hit', name.name, flush=True)
        return np.memmap(name, dtype=np.int32, mode='r', shape=shape)
    result = _original_calc_prev(csr, n_nodes, args)
    stored = np.memmap(name, dtype=np.int32, mode='w+', shape=shape)
    for start in range(0, len(result), 64): stored[start:start+64] = result[start:start+64]
    stored.flush()
    name.with_suffix('.complete').touch()
    return stored
module_traf.calc_prev = cached_calc_prev

class Var:
    def __init__(self,value):self.value=value
    def get(self):return self.value
    def set(self,value):self.value=value
class Widget(dict):
    def configure(self,**kwargs):pass
class Tk:
    def after(self,*args,**kwargs):pass
    def destroy(self):pass
class Headless(tfs.Root):
    def __init__(self):
        self.moduleNames=['FS','SIF','SHIP','TOUR','PARCEL_DMND','PARCEL_SCHD','SERVICE','TRAF','OUTP']
        self.controlFile=Var(str(config));self.progressBar=Widget();self.statusBar=Widget();self.root=Tk();self.failed=False
    def update_statusbar(self,*args):pass
    def error_screen(self,text='',**kwargs):self.failed=True;print(text,flush=True)
if __name__=='__main__':
    root=Headless();root.actually_run_main();sys.exit(int(root.failed))
