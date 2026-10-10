#!/usr/bin/env python3
"""Bounded full-core bootstrap scaling with matched outputs and sampled RSS."""
import argparse,datetime as dt,json,os,resource,subprocess,time,statistics
from pathlib import Path
from common import ROOT,save,sha256
from phase1_differential import compare_output
from phase2_common import clean_env

ARGS=['-p','4+5*3+4','-N','30','-t','15','-r','4','-I','0']

def cpu():
 r=resource.getrusage(resource.RUSAGE_CHILDREN);return r.ru_utime+r.ru_stime

def rss(pid):
 try:
  for line in Path(f'/proc/{pid}/status').read_text().splitlines():
   if line.startswith('VmRSS:'):return int(line.split()[1])
 except (FileNotFoundError,ProcessLookupError):pass
 return 0

def datasets():
 old=json.loads(Path('bench/cpu-campaign-validation.json').read_text())
 original=dict(id='original',input='tests/fixtures/blocks.psmcfa',seed=20261009,materialized=[f'tests/fixtures/bootstrap/replicate-{i:02d}.psmcfa' for i in range(30)],oracles=[str(Path(old['run_directory'])/'cpu-raw'/f'K23_N30_bootstrap_{i:02d}-oracle.psmc') for i in range(30)],nonfinite=3)
 h=json.loads(Path('bench/cpu-campaign-hmm-fixtures.json').read_text())
 cases=[c for c in h['cases'] if c['id']!='hmm-unsplit-k23-n30']
 assert len(cases)==30
 hmm=dict(id='model-based',input='tests/fixtures/cpu-campaign-hmm/blocks-4000.psmcfa',seed=20261011,materialized=[c['input'] for c in cases],oracles=[next(r['output'] for r in c['runs'] if r['label']=='vanilla') for c in cases],nonfinite=1)
 return [original,hmm]

def batch(binary,label,case,workers,affinity,out,order='forward'):
 out.mkdir(parents=True)
 commands=[]
 if label=='vanilla':
  commands=[[binary,'-o',str(out/f'replicate-{i:02d}.psmc'),*ARGS,p] for i,p in enumerate(case['materialized'])]
 else:
  commands=[[binary,'bootstrap','--backend','cpu','--simd','auto','--workers',str(workers),'--replicates','30','--seed',str(case['seed']),'--memory-mib','2048','--task-order',order,'--output-dir',str(out/'fits'),*ARGS,case['input']]]
 queued=list(enumerate(commands));active=[];peak=0;max_active=0
 start=time.perf_counter();before=cpu()
 while queued or active:
  while queued and len(active)<workers:
   i,command=queued.pop(0)
   stdout=(out/f'child-{i}.stdout').open('wb');stderr=(out/f'child-{i}.stderr').open('wb')
   p=subprocess.Popen(command,env=clean_env(),stdout=stdout,stderr=stderr,preexec_fn=lambda:os.sched_setaffinity(0,affinity))
   active.append((p,stdout,stderr,command))
  max_active=max(max_active,len(active));peak=max(peak,sum(rss(p.pid) for p,_,_,_ in active))
  remaining=[]
  for p,stdout,stderr,command in active:
   rc=p.poll()
   if rc is None:remaining.append((p,stdout,stderr,command))
   else:
    stdout.close();stderr.close();assert rc==0,(command,rc)
  active=remaining
  if active:time.sleep(.01)
 wall=time.perf_counter()-start;spent=cpu()-before
 fits=out if label=='vanilla' else out/'fits'
 for i,oracle in enumerate(case['oracles']):compare_output(Path(oracle).read_bytes(),(fits/f'replicate-{i:02d}.psmc').read_bytes())
 manifest=None
 if label!='vanilla':
  manifest=json.loads((fits/'manifest.json').read_text())
  assert manifest['workers']==min(workers,len(affinity),30)
  assert manifest['failed_replicates']==0 and manifest['nonfinite_replicates']==case['nonfinite']
  assert [r['index'] for r in manifest['replicates']]==list(range(30))
  for i in range(30):assert json.loads((fits/f'replicate-{i:02d}.stats.json').read_text())['simd_selected']=='avx'
 return dict(wall_seconds=wall,cpu_seconds=spent,sampled_aggregate_rss_kib=peak,commands=commands,max_concurrent_processes=max_active,actual_workers=None if manifest is None else manifest['workers'],output_directory=str(out),all_30_exact=True)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['scaling','candidate'],default='scaling');parser.add_argument('--candidate');parser.add_argument('--repeats',type=int,default=3);o=parser.parse_args()
 os.chdir(ROOT);allowed=sorted(os.sched_getaffinity(0));assert len(allowed)>1
 phys=[];seen=set()
 for c in allowed:
  core=(Path(f'/sys/devices/system/cpu/cpu{c}/topology/physical_package_id').read_text().strip(),Path(f'/sys/devices/system/cpu/cpu{c}/topology/core_id').read_text().strip())
  if core not in seen:seen.add(core);phys.append(c)
 raw=Path('bench/parallel')/(o.mode+'-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));raw.mkdir()
 binaries={'baseline':'bench/parallel/baseline','vanilla':'work/vanilla/psmc'}
 if o.candidate:binaries['balanced']=o.candidate
 digests={k:sha256(p) for k,p in binaries.items()}
 report=dict(status='running',allowed_cpus=allowed,physical_representatives=phys,nice=os.nice(0),mode=o.mode,binaries={k:dict(path=p,sha256=digests[k]) for k,p in binaries.items()},raw_directory=str(raw),runner_sha256=sha256(__file__),cases=[],limitations=['Shared host; no parallel independent benchmark groups. Each group deliberately uses multiple workers.','RSS is sampled at 10ms and is a lower bound on peak total live child-process RSS, excluding the Python controller. Rust threads share one process; vanilla uses independent processes.','CPU is summed child process user+system time; wall includes launch, IO and output generation, excludes correctness comparison.','Original batch retains 3 nonfinite cases; model-based batch retains 1. No omitted seeds, changed rounds or parallel throughput inferred from serial speed.'])
 path='bench/parallel-'+o.mode+'.json'
 for case in datasets():
  configs=([(1,allowed), (4,allowed),(8,allowed),(len(phys),allowed),(len(allowed),allowed),(len(phys),phys)] if o.mode=='scaling' else [(len(allowed),allowed),(len(phys),phys)])
  for workers,affinity in configs:
   labels=['baseline'] if o.mode=='scaling' else ['baseline','balanced','vanilla']
   entry=dict(dataset=case['id'],workers=workers,affinity=affinity,input_sha256=sha256(case['input']),materialized_sha256={p:sha256(p) for p in case['materialized']},oracle_sha256={p:sha256(p) for p in case['oracles']},runs=[]);report['cases'].append(entry)
   for rep in range(o.repeats+1):
    for label in labels[rep%len(labels):]+labels[:rep%len(labels)]:
     assert sha256(binaries[label])==digests[label]
     result=batch(binaries[label],label,case,workers,affinity,raw/f'{case["id"]}-w{workers}-a{len(affinity)}-{rep}-{label}',order='balanced' if label=='balanced' else 'forward')
     entry['runs'].append(dict(label=label,repeat=rep,warmup=rep==0,load_average=list(os.getloadavg()),**result));save(path,report)
   entry['summary']={label:{field:dict(median=statistics.median(vals),minimum=min(vals),maximum=max(vals)) for field in ['wall_seconds','cpu_seconds','sampled_aggregate_rss_kib'] for vals in [[r[field] for r in entry['runs'] if r['label']==label and not r['warmup']]]} for label in labels}
   save(path,report);print(json.dumps({k:entry[k] for k in ['dataset','workers','affinity','summary']}),flush=True)
 report['status']='passed';save(path,report)

if __name__=='__main__':main()
