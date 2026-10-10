#!/usr/bin/env python3
"""Sequential SIMD CLI/selection and output-preservation controls (self-review)."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
from common import ROOT, save, sha256
from phase1_differential import compare_output
from phase2_common import clean_env, utc_stamp, relative
from phase3_common import resource_policy


def main():
    os.chdir(ROOT)
    policy = resource_policy()
    binary = Path('target/release/psmc-rs')
    digest = sha256(binary)
    raw = Path('work/cpu-next-gates/review')/utc_stamp()
    raw.mkdir(parents=True)
    checks=[]
    def run(args, name):
        assert sha256(binary)==digest
        r=subprocess.run([str(binary),*args],env=clean_env(),capture_output=True)
        (raw/(name+'.psmc')).write_bytes(r.stdout)
        (raw/(name+'.stderr')).write_bytes(r.stderr)
        return r
    for n in [1,2,3,4,5,6,7,8,9,23,64]:
        args=['--backend','cpu','--seed','42','-p',f'{n}*1','-N','1','-I','0','tests/fixtures/tiny.psmcfa']
        oracle=subprocess.run(['work/vanilla/psmc',*args[4:]],env=clean_env(),capture_output=True)
        assert oracle.returncode==0
        (raw/f'n{n}-oracle.psmc').write_bytes(oracle.stdout)
        for mode in ['auto','off','avx']:
            stats=raw/f'n{n}-{mode}.stats.json'
            r=run(['--simd',mode,'--stats',str(stats),*args],f'n{n}-{mode}')
            assert r.returncode==0,r.stderr
            comparison=compare_output(oracle.stdout,r.stdout)
            values=json.loads(stats.read_text())
            expected='avx' if n>=4 and mode!='off' else 'scalar'
            assert values['simd_requested']==mode and values['simd_selected']==expected
            checks.append(dict(name=f'states-{n}-{mode}',passed=True,selected=expected,**comparison))
    for name,args in [('invalid',['--backend','cpu','--simd','bad']),('dense-forced-avx',['--backend','dense','--simd','avx'])]:
        out=raw/(name+'.existing-output');out.write_text('KEEP\n')
        r=run([*args,'-o',str(out),'-N','0','tests/fixtures/tiny.psmcfa'],name)
        assert r.returncode!=0 and out.read_text()=='KEEP\n'
        checks.append(dict(name=name,passed=True,returncode=r.returncode,output_preserved=True))
    outputs=[]
    for mode in ['off','auto','avx']:
        out=raw/('batch-'+mode)
        r=run(['bootstrap','--backend','cpu','--simd',mode,'--workers','1','--replicates','3','--seed','42','--output-dir',str(out),'-p','4+5*3+4','-N','2','-I','0.1','tests/fixtures/blocks.psmcfa'],'batch-'+mode)
        assert r.returncode==0,r.stderr
        manifest=json.loads((out/'manifest.json').read_text())
        assert manifest['workers']==manifest['requested_workers']==1 and manifest['failed_replicates']==0
        current=[(out/f'replicate-{i:02d}.psmc').read_bytes() for i in range(3)]
        if outputs:
            for a,b in zip(outputs,current):compare_output(a,b)
        outputs=current
        for i in range(3):
            stats=json.loads((out/f'replicate-{i:02d}.stats.json').read_text())
            assert stats['simd_requested']==mode
            assert stats['simd_selected']==('scalar' if mode=='off' else 'avx')
        checks.append(dict(name='batch-'+mode,passed=True,workers=1,replicates=3))
    report=dict(status='passed',scope='Self-review of SIMD CLI and one-worker integration on AVX hardware; absence-of-AVX dispatch is a unit-test simulation, other hardware not_run.',created_utc=dt.datetime.now(dt.timezone.utc).isoformat(),binary_sha256=digest,resource_policy=policy,checks=checks,raw_directory=str(raw),runner_sha256=sha256(Path(__file__)))
    save('bench/cpu-next-review.json',report)
    print(json.dumps({'status':'passed','checks':len(checks)},indent=2))

if __name__=='__main__':main()
