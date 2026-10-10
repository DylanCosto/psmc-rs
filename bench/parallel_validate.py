#!/usr/bin/env python3
"""Seeded C equality, order and resource-admission controls for parallel queues."""
import argparse,datetime as dt,json,os,subprocess
from pathlib import Path
from common import ROOT,save,sha256
from phase2_common import clean_env,source_hashes
from phase1_differential import compare_output


def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',required=True);o=p.parse_args();os.chdir(ROOT)
 raw=Path('bench/parallel')/('validation-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));raw.mkdir()
 binary=o.candidate;digest=sha256(binary);oracle='work/instrumented/psmc'
 result=dict(status='running',binary=dict(path=binary,sha256=digest),oracle=dict(path=oracle,sha256=sha256(oracle)),allowed_cpus=sorted(os.sched_getaffinity(0)),source_sha256=source_hashes(),runner_sha256=sha256(__file__),raw_directory=str(raw),checks=[])
 report='bench/parallel-validation.json'
 def call(command,name,env=None):
  r=subprocess.run(command,env=env or clean_env(),capture_output=True)
  (raw/(name+'.stdout')).write_bytes(r.stdout);(raw/(name+'.stderr')).write_bytes(r.stderr)
  assert r.returncode==0,(command,r.stderr.decode())
  return r.stdout
 for pattern,label in [('4+5*3+4','k23'),('4+25*2+4+6','k64')]:
  args=['-p',pattern,'-N','2','-I','0.1','-t','15','-r','4'];input='tests/fixtures/blocks.psmcfa';expected=[]
  for i in range(30):expected.append(call([oracle,'-b',*args,input],f'{label}-c-{i}',{**clean_env(),'PSMC_SEED':str(20261009+i)}))
  reference_draws=None
  for workers,order,backend,cache,simd in [(1,'balanced','cpu','on','auto'),(4,'balanced','cpu','on','auto'),(16,'balanced','cpu','on','auto'),(16,'reverse','cpu','off','off'),(16,'forward','dense','off','off')]:
   name=f'{label}-w{workers}-{order}-{backend}';out=raw/name
   cmd=[binary,'bootstrap','--backend',backend,'--simd',simd,'--cache',cache,'--workers',str(workers),'--task-order',order,'--seed','20261009','--replicates','30','--memory-mib','2048','--output-dir',str(out),*args,input]
   call(cmd,name)
   m=json.loads((out/'manifest.json').read_text());assert m['workers']==min(workers,len(os.sched_getaffinity(0))) and m['failed_replicates']==0
   comparisons=[compare_output(expected[i],(out/f'replicate-{i:02d}.psmc').read_bytes()) for i in range(30)]
   draws=[(out/f'replicate-{i:02d}.draws.jsonl').read_bytes() for i in range(30)]
   if reference_draws is None:reference_draws=draws
   else:assert draws==reference_draws
   result['checks'].append(dict(name=name,command=cmd,manifest_sha256=sha256(out/'manifest.json'),comparisons=comparisons,all_draws_equal=True,actual_workers=m['workers']))
   save(report,result);print(name+' passed',flush=True)
 # Admission is checked before creating the output directory, also for balanced.
 base=[binary,'bootstrap','--backend','cpu','--task-order','balanced','--seed','42','--workers','999','--replicates','2','-N','0','-I','0']
 for memory,success in [(1,False),(21,True)]:
  name='memory-'+str(memory);out=raw/name;cmd=[*base,'--memory-mib',str(memory),'--output-dir',str(out),'tests/fixtures/blocks.psmcfa']
  r=subprocess.run(cmd,env=clean_env(),capture_output=True);(raw/(name+'.stderr')).write_bytes(r.stderr)
  if success:
   assert r.returncode==0,r.stderr
   m=json.loads((out/'manifest.json').read_text());assert m['workers']==1
  else:assert r.returncode!=0 and not out.exists()
  result['checks'].append(dict(name=name,command=cmd,returncode=r.returncode,passed=True))
 assert sha256(binary)==digest
 result['status']='passed';save(report,result)

if __name__=='__main__':main()
