"""Measured full-core CPU control for the batched resident-message GPU probe."""
import json,os,subprocess,statistics
from pathlib import Path
from common import ROOT,save,sha256,timed_run
from phase2_common import clean_env
os.chdir(ROOT)
scratch=Path('work/exhaust/cpu/baseline');example=scratch/'crates/psmc-cpu/examples/exhaust_resident_cpu.rs'
assert not example.exists();example.write_bytes(Path('bench/exhaust_resident_cpu.rs').read_bytes())
cmd=['cargo','build','--release','--locked','--offline','-p','psmc-cpu','--example','exhaust_resident_cpu']
log=Path('work/exhaust/resident-cpu-build.log')
with log.open('w') as stream:subprocess.run(cmd,cwd=scratch,env=clean_env(),stdout=stream,stderr=subprocess.STDOUT,check=True)
binary=str(scratch/'target/release/examples/exhaust_resident_cpu')
r=dict(status='running',source_sha256=sha256(example),binary_sha256=sha256(binary),build_command=cmd,runs=[],scope='Same 50001-site K64 synthetic model/observations as GPU probe; independent tasks with per-worker workspace. Includes CPU emission counts and log-likelihood; GPU probe omits those, so this comparison favors GPU.')
for jobs in [1,8,16,32]:
    for workers in sorted(set([min(jobs,16),min(jobs,10)])):
        for rep in range(4):
            cmd=[binary,str(jobs),str(workers)];p=subprocess.run(cmd,env=clean_env(),capture_output=True,text=True,check=True)
            value=json.loads(p.stdout);value.update(command=cmd,repeat=rep);r['runs'].append(value);save('bench/exhaust-resident-cpu.json',r)
r['medians']=[dict(jobs=jobs,workers=workers,seconds=statistics.median(x['seconds'] for x in r['runs'] if x['jobs']==jobs and x['workers']==workers and x['repeat']>0)) for jobs,workers in sorted({(x['jobs'],x['workers']) for x in r['runs']})]
r['status']='measured';save('bench/exhaust-resident-cpu.json',r);print(r['medians'],flush=True)
