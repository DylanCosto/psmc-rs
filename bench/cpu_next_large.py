#!/usr/bin/env python3
"""Held-out full HG002 chr1 N30 exactness; timings descriptive, not repeated claim."""
import argparse,json,os
from pathlib import Path
from common import ROOT,save,sha256,timed_run,read_fasta,write_fasta,draw_bootstrap
from phase2_common import clean_env
from phase1_differential import compare_output
from hg_benchmark import ARGS
import subprocess

def main():
    os.chdir(ROOT);p=argparse.ArgumentParser();p.add_argument('--candidate',required=True);o=p.parse_args()
    manifest=json.loads(Path('bench/cpu-next-hg002-input.json').read_text());inp=manifest['output'];assert sha256(inp['path'])==inp['sha256']
    raw=Path('work/cpu-next/large');raw.mkdir()
    # Predeclare future bootstrap procedure and fixed samples, without implying
    # these new HG002 replicate fits have been run in this full-record gate.
    blocks=raw/'blocks-50000.psmcfa';cmd=['work/vanilla/utils/splitfa',inp['path'],'50000'];blocks.write_bytes(subprocess.check_output(cmd));records=read_fasta(blocks)
    assert ''.join(s for _,s in records)==read_fasta(inp['path'])[0][1]
    reps=[]
    for i in range(30):
        indices,draws=draw_bootstrap(records,20261101+i);dest=raw/f'bootstrap-{i:02d}.psmcfa';write_fasta(dest,[records[j] for j in indices]);reps.append(dict(index=i,seed=20261101+i,indices=indices,draws=draws,path=str(dest),sha256=sha256(dest)))
    save('bench/cpu-next-hg002-sampling.json',dict(status='prepared_not_fitted',runner_sha256=sha256(__file__),input_sha256=inp['sha256'],split_command=cmd,split_binary_sha256=sha256(cmd[0]),blocks=str(blocks),blocks_sha256=sha256(blocks),source_record_count=len(records),seed=20261101,replicates=reps,rationale='Same 50000-bin bootstrap splitting convention as HG001; all remainders/masks retained. Samples pinned before any fitting; this campaign validates the original whole chromosome, not these bootstrap fits.'))
    binaries={'vanilla':'work/vanilla/psmc','baseline':'work/cpu-next/baseline','candidate':o.candidate}
    r=dict(status='running',runner_sha256=sha256(__file__),input_manifest_sha256=sha256('bench/cpu-next-hg002-input.json'),binaries={k:dict(path=v,sha256=sha256(v)) for k,v in binaries.items()},runs=[],limitations=['One complete original chromosome fit per executable, K64/N30. Timings descriptive only; no repeated large-input speed claim.','The single record remains continuous through all masks; 2,489,565 bins.','Prepared HG002 bootstrap samples are not fitted in this gate. The separate repeated full 30-bootstrap acceptance uses HG001.'])
    oracle=None
    for label,binary in binaries.items():
        command=['taskset','-c','0',binary]+([] if label=='vanilla' else ['--backend','cpu','--simd','auto'])+ARGS+[inp['path']]
        run=timed_run(command,ROOT/raw/label,env=clean_env(),timeout=3600);assert run['exit_code']==0
        if oracle is None:oracle=Path(run['output']).read_bytes()
        else:run['comparison']=compare_output(oracle,Path(run['output']).read_bytes())
        assert not run['nonfinite_records_beyond_initial_RI'];run.update(label=label,cpu_seconds=run['user_seconds']+run['system_seconds']);r['runs'].append(run);save('bench/cpu-next-large.json',r);print(json.dumps({k:run[k] for k in ['label','wall_seconds','cpu_seconds','peak_rss_kib']}),flush=True)
    r['status']='passed';save('bench/cpu-next-large.json',r)
if __name__=='__main__':main()
