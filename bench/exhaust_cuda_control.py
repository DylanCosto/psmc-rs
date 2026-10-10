"""Check the final optional CUDA build after shared CPU message changes."""
import os,json,subprocess
from pathlib import Path
from common import ROOT,save,sha256,timed_run
from phase2_common import clean_env
from phase1_differential import compare_output
os.chdir(ROOT);raw=Path('work/exhaust/cuda-control');raw.mkdir()
build=json.load(open('bench/exhaust-final-build.json'));binary=build['binaries']['cuda']['path'];assert sha256(binary)==build['binaries']['cuda']['sha256']
env={**clean_env(),'PSMC_NVRTC_LIBRARY':json.load(open('bench/cuda-environment.json'))['nvrtc_path']}
r=dict(status='running',binary=binary,binary_sha256=sha256(binary),cases=[])
for name,inp,oracle in [('hg001','work/hg-input/NA12878_chr22.psmcfa','bench/hg/pilot/vanilla.psmc'),('hg002','work/cpu-next/hg002/HG002_GRCh38_chr1.psmcfa','work/cpu-next/large/vanilla.psmc')]:
    cmd=[binary,'--backend','cuda','--seed','42','-p','4+25*2+4+6','-N','30','-t','15','-r','5','-I','0',inp]
    run=timed_run(cmd,ROOT/raw/name,env=env,timeout=1800);assert run['exit_code']==0
    run.update(input_sha256=sha256(inp),oracle=oracle,oracle_sha256=sha256(oracle),comparison=compare_output(Path(oracle).read_bytes(),Path(run['output']).read_bytes()));r['cases'].append(run);save('bench/exhaust-cuda-control.json',r);print('CUDA control',name,run['wall_seconds'],flush=True)
cmd=[build['binaries']['cpu']['path'],'--backend','cuda','tests/fixtures/tiny.psmcfa'];p=subprocess.run(cmd,env=env,capture_output=True);assert p.returncode!=0 and b'cuda' in p.stderr.lower();r['cpu_only_rejects_cuda']=dict(command=cmd,returncode=p.returncode,stderr=p.stderr.decode())
r['status']='passed';save('bench/exhaust-cuda-control.json',r)
