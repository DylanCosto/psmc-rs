#!/usr/bin/env python3
"""Sequential complete acceptance gates; preserve every historical report."""
import os
import re
from pathlib import Path
import subprocess
from common import ROOT, save, sha256


def main():
    os.chdir(ROOT)
    raw=Path('work/cpu-next-gates');raw.mkdir(exist_ok=True)
    commands=[
        ['cargo','fmt','--all','--check'],
        ['cargo','test','--workspace','--locked','--offline'],
        ['cargo','test','--workspace','--release','--locked','--offline'],
        ['cargo','clippy','--workspace','--all-targets','--locked','--offline','--','-W','clippy::almost_swapped'],
        ['cargo','build','--release','--bins','--examples','--locked','--offline'],
        ['taskset','-c','0','python3','bench/cpu_next_build.py'],
        ['taskset','-c','0','python3','bench/phase3_validate.py','--run','--report','bench/cpu-next-validation.json'],
        ['taskset','-c','0','python3','bench/cpu_next_extended_gate.py'],
        ['taskset','-c','0','python3','bench/phase3_scheduler.py','--run','--validation','bench/cpu-next-validation.json','--report','bench/cpu-next-scheduler.json'],
        ['taskset','-c','0','python3','bench/cpu_next_review.py'],
    ]
    report=dict(status='running',runner_sha256=sha256(__file__),steps=[],policy='Build and unit tests use available CPUs; legacy exactness harnesses retain their own one-CPU policy. All steps sequential; no overlapping timed workloads.')
    for i,command in enumerate(commands):
        log=raw/f'step-{i}.log'
        print('START '+str(command),flush=True)
        with log.open('w') as f: result=subprocess.run(command,env={**os.environ,'CARGO_BUILD_JOBS':'16','RUST_TEST_THREADS':'16'},stdout=f,stderr=subprocess.STDOUT)
        report['steps'].append(dict(command=command,returncode=result.returncode,log=str(log),sha256=sha256(log)))
        save('bench/cpu-next-gates.json',report)
        assert result.returncode==0,command
        print('PASS '+str(command),flush=True)
    binary='target/release/psmc-rs'
    dis=subprocess.check_output(['objdump','-d','-C',binary],text=True)
    ops=re.findall(r'\t([a-z][a-z0-9]+)\s',dis)
    fma=sum(o.startswith(('vfm','vfnm')) for o in ops)
    horizontal=sum(o.startswith(('vhadd','vhsub','hadd','hsub')) for o in ops)
    packed=sum(o in ['vaddpd','vmulpd','vdivpd'] for o in ops)
    assert fma==horizontal==0 and packed>0
    report['assembly']=dict(binary_sha256=sha256(binary),command=['objdump','-d','-C',binary],fma_ops=fma,horizontal_ops=horizontal,packed_avx_ops=packed)
    report['status']='passed';save('bench/cpu-next-gates.json',report)

if __name__=='__main__': main()
