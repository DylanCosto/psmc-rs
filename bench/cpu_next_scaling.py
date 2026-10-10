#!/usr/bin/env python3
"""Complete 30-replicate worker/affinity screen on the frozen paired binaries."""
import argparse,json,os
from pathlib import Path
from common import ROOT,sha256,save
from phase1_differential import compare_output
import hg_benchmark as hg

def main():
    os.chdir(ROOT);p=argparse.ArgumentParser();p.add_argument('--candidate',required=True);o=p.parse_args()
    raw=Path('work/cpu-next/scaling');raw.mkdir()
    inputs=json.loads(Path('bench/hg-input.json').read_text());old=json.loads(Path('bench/hg-benchmark.json').read_text())
    for item in inputs['replicates']:assert sha256(item['path'])==item['sha256']
    for item in old['canonical_outputs']:assert sha256(item['path'])==item['sha256']
    binaries={'baseline':'work/cpu-next/baseline','candidate':o.candidate}
    r=dict(status='running',runner_sha256=sha256(__file__),inherited_runner_sha256=sha256('bench/hg_benchmark.py'),binaries={k:dict(path=v,sha256=sha256(v)) for k,v in binaries.items()},runs=[],limitations=['Single complete batch per worker/affinity and binary; exploratory screen only. Repeated matched acceptance remains separate.','30 fixed HG001 chromosome22 bootstraps, K64/N30, all exact C outputs required.','Shared host; independent groups sequential.'])
    physical=[0,2,4,6,8,10,12,13,14,15];allowed=sorted(os.sched_getaffinity(0));assert allowed==list(range(16))
    for idx,(workers,affinity) in enumerate([(8,allowed),(10,physical),(16,allowed)]):
        for label in (['baseline','candidate'] if idx%2==0 else ['candidate','baseline']):
            hg.BINARIES['rust']=binaries[label];hg.EXPECTED['rust']=r['binaries'][label]['sha256']
            run=hg.run_batch('rust',workers,inputs,raw/f'{label}-{workers}',affinity)
            run['comparisons']=[compare_output(Path(c['path']).read_bytes(),Path(a['path']).read_bytes()) for c,a in zip(old['canonical_outputs'],run['outputs'])]
            assert all(not v['nonfinite'] for v in run['outputs']);run.update(label=label,all_30_exact=True)
            r['runs'].append(run);save('bench/cpu-next-scaling.json',r);print(json.dumps({k:run[k] for k in ['label','workers','wall_seconds','cpu_seconds','sampled_aggregate_rss_kib']}),flush=True)
    r['status']='passed';save('bench/cpu-next-scaling.json',r)
if __name__=='__main__':main()
