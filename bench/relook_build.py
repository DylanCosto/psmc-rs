"""Freeze the reviewable CPU candidate; do not replace installed binaries."""
import os,json,subprocess,shutil,re
from pathlib import Path
from common import ROOT,save,sha256
from phase2_common import clean_env
os.chdir(ROOT);raw=Path('work/relook/final-build');raw.mkdir()
env={**clean_env(),'PSMC_NVRTC_LIBRARY':json.load(open('bench/cuda-environment.json'))['nvrtc_path']}
commands=[['cargo','fmt','--all'],['cargo','test','--workspace','--locked','--offline'],['cargo','test','--workspace','--release','--locked','--offline','--','--include-ignored','--test-threads=1'],['cargo','build','--release','--locked','--offline','-p','psmc-cli','--features','cuda'],['cargo','build','--release','--locked','--offline','--bins','--examples']]
r=dict(status='running',runner_sha256=sha256(__file__),steps=[],binaries={})
for i,cmd in enumerate(commands):
    log=raw/f'step-{i}.log'
    with log.open('w') as f:p=subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT)
    r['steps'].append(dict(command=cmd,returncode=p.returncode,log=str(log),sha256=sha256(log)));save('bench/relook-build.json',r);assert p.returncode==0
    if i in [3,4]:
        label='cuda' if i==3 else 'cpu';dest=raw/('psmc-rs-'+label);shutil.copy2('target/release/psmc-rs',dest)
        r['binaries'][label]=dict(path=str(dest),sha256=sha256(dest))
    print('final build step',i,flush=True)
s=subprocess.check_output(['objdump','-d','-C',r['binaries']['cpu']['path']],text=True);ops=re.findall(r'\t([a-z][a-z0-9]+)\s',s)
r['assembly']=dict(fma=sum(o.startswith(('vfm','vfnm')) for o in ops),horizontal=sum(o.startswith(('vhadd','vhsub','hadd','hsub')) for o in ops),packed_avx=sum(o in ['vaddpd','vmulpd','vdivpd'] for o in ops));assert r['assembly']['fma']==r['assembly']['horizontal']==0 and r['assembly']['packed_avx']>0
r['source_sha256']={str(p.relative_to(ROOT)):sha256(p) for p in ROOT.glob('crates/**/*.rs')};r['configuration_sha256']={s:sha256(s) for s in ['Cargo.toml','Cargo.lock','rust-toolchain.toml']}
r['status']='passed';save('bench/relook-build.json',r)
