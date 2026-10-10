"""Read retained C trajectories to bound full-candidate memoization benefits."""
import gzip,json,struct
from pathlib import Path
from common import sha256,save
out={}
for name in ['tiny_N2','grid_N1','K23_N1','K64_N1']:
    path=Path('work/cuda/final-gates')/(name+'-C.jsonl.gz')
    seen=set();total=hits=adjacent=0;prev=None
    with gzip.open(path,'rt') as stream:
        for line in stream:
            if '"event":"objective"' not in line:continue
            r=json.loads(line);key=(r['iteration'],tuple(struct.pack('d',float(x)) for x in r['params']))
            hits+=key in seen;adjacent+=key==prev;seen.add(key);prev=key;total+=1
    out[name]=dict(total=total,repeats=hits,adjacent=adjacent,path=str(path),sha256=sha256(path))
save('bench/exhaust-objective-reuse.json',out);print(out)
