"""Larger held-out input attribution using the retained verified diagnostic build."""
import os,json
from pathlib import Path
from common import ROOT,save,sha256,timed_run
from phase2_common import clean_env
from phase1_differential import compare_output
os.chdir(ROOT)
raw=Path('work/exhaust/profile');raw.mkdir(parents=True)
old=json.loads(Path('bench/cuda-profile.json').read_text())
binary='work/cuda/profile/source/target/release/psmc-rs'
assert sha256(binary)==old['instrumented_binary_sha256']
source='work/cpu-next/hg002/HG002_GRCh38_chr1.psmcfa';oracle='work/cpu-next/large/vanilla.psmc'
r=dict(status='running',diagnostic_provenance_sha256=sha256('bench/cuda-profile.json'),binary_sha256=sha256(binary),input_sha256=sha256(source),oracle_sha256=sha256(oracle),runs=[])
for rep in range(2):
    dest=ROOT/raw/f'hg002-{rep}';profile=str(dest)+'.json'
    cmd=['taskset','-c','0',binary,'--backend','cpu','--seed','42','-p','4+25*2+4+6','-N','30','-t','15','-r','5','-I','0',source]
    run=timed_run(cmd,dest,env={**clean_env(),'PSMC_CPU_DIAGNOSTIC':profile},timeout=1800)
    assert run['exit_code']==0
    compare_output(Path(oracle).read_bytes(),Path(run['output']).read_bytes())
    run.update(exact=True,profile=json.loads(Path(profile).read_text()));r['runs'].append(run);save('bench/exhaust-profile.json',r);print('HG002 profile',rep,run['wall_seconds'],flush=True)
r['status']='passed';save('bench/exhaust-profile.json',r)
