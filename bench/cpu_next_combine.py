#!/usr/bin/env python3
"""Confirm whether the two independently promising K64 widths combine usefully."""
import io,json,os,statistics,subprocess,tarfile
from pathlib import Path
from common import ROOT,save,sha256,timed_run
from phase2_common import clean_env
from phase1_differential import compare_output
from cpu_next_candidates import prepare,BASE

def main():
    os.chdir(ROOT);r0=json.loads(Path('bench/cpu-next-screen.json').read_text());assert r0['status']=='passed'
    raw=Path('work/cpu-next/combined');raw.mkdir();scratch=raw/'source';scratch.mkdir()
    data=subprocess.check_output(['git','archive',BASE,'Cargo.toml','Cargo.lock','rust-toolchain.toml','crates'])
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:tar.extractall(scratch,filter='data')
    prepare(scratch,'counts32s8');prepare(scratch,'messages32')
    commands=[['cargo','fmt','--all'],['cargo','test','--workspace','--offline'],['cargo','test','--workspace','--release','--offline'],['cargo','build','--release','--bins','--examples','--offline']]
    logs=[]
    for i,cmd in enumerate(commands):
        log=raw/f'build-{i}.log'
        with log.open('w') as f:subprocess.run(cmd,cwd=scratch,stdout=f,stderr=subprocess.STDOUT,env={**clean_env(),'CARGO_BUILD_JOBS':'16','RUST_TEST_THREADS':'16'},check=True)
        logs.append(dict(path=str(log),sha256=sha256(log)))
    binaries={k:v for k,v in r0['variants'].items() if k in ['baseline','messages32']};binary=scratch/'target/release/psmc-rs';binaries['combined']=dict(binary=str(binary),sha256=sha256(binary),source={str(p.relative_to(scratch)):sha256(p) for p in (scratch/'crates').rglob('*.rs')})
    case=next(c for c in r0['cases'] if c['id']=='hg-bootstrap01');assert sha256(case['input'])==case['input_sha256'];assert sha256(case['oracle'])==case['oracle_sha256']
    r=dict(status='running',runner_sha256=sha256(__file__),generator_sha256=sha256('bench/cpu_next_candidates.py'),binaries=binaries,case=case,commands=commands,logs=logs,runs=[])
    labels=list(binaries)
    for rep in range(4):
        for label in labels[rep%3:]+labels[:rep%3]:
            entry=binaries[label];assert sha256(entry['binary'])==entry['sha256']
            cmd=['taskset','-c','0',entry['binary'],'--backend','cpu','--simd','auto','--seed','42',*case['args'],case['input']]
            run=timed_run(cmd,ROOT/raw/f'{rep}-{label}',env=clean_env(),timeout=600);assert run['exit_code']==0
            compare_output(Path(case['oracle']).read_bytes(),Path(run['output']).read_bytes());run.update(label=label,repeat=rep,exact=True,cpu_seconds=run['user_seconds']+run['system_seconds']);r['runs'].append(run);save('bench/cpu-next-combination.json',r);print(json.dumps({k:run[k] for k in ['label','repeat','wall_seconds','cpu_seconds']}),flush=True)
    r['summary']={label:{key:dict(median=statistics.median(v),minimum=min(v),maximum=max(v)) for key in ['wall_seconds','cpu_seconds'] for v in [[run[key] for run in r['runs'] if run['repeat']>0 and run['label']==label]]} for label in labels};r['status']='passed';save('bench/cpu-next-combination.json',r)
if __name__=='__main__':main()
