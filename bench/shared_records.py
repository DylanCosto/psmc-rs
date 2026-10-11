#!/usr/bin/env python3
"""Exactness and paired performance of the cooperative record scheduler."""
import argparse,json,os,statistics
from pathlib import Path
from common import ROOT,save,sha256,timed_run,read_fasta,draw_bootstrap
from equivalent_c_baseline import ARGS
from phase2_common import clean_env
from phase1_differential import compare_output

def main():
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['validation','performance','screen']);ap.add_argument('--variant',default='');ap.add_argument('--screen-mode',choices=['both','equivalent','strict'],default='both');a=ap.parse_args();os.chdir(ROOT)
 tag=(a.variant+'-' if a.variant else '')+a.stage;raw=Path('work/shared-records')/tag;raw.mkdir();report=f'bench/shared-records-{tag}.json';binary='work/shared-records/candidate'
 c=json.load(open('bench/equivalent-c-baseline.json'));r=dict(status='running',binary_sha256=sha256(binary),runner_sha256=sha256(__file__),protocol_sha256=sha256('docs/shared-record-scheduling.md'),runs=[])
 def run(cmd,tag):
  x=timed_run(cmd,ROOT/raw/tag,env=clean_env(),timeout=3600);assert x['exit_code']==0,x;x['tag']=tag;x['cpu_seconds']=x['user_seconds']+x['system_seconds'];r['runs'].append(x);save(report,r);print(tag,round(x['wall_seconds'],3),flush=True);return x
 def batch(label,mode,scheduler,tag,extra=()):
  ds=c['datasets'][label];dest=raw/tag
  x=run(['taskset','-c','0-15',binary,'bootstrap','--mode',mode,'--scheduler',scheduler,'--workers','16','--memory-mib','16384','--replicates','30','--seed',str(ds['samples'][0]['seed']),'--output-dir',str(dest),*extra,*ARGS,ds['blocks']],tag+'-time')
  m=json.load(open(dest/'manifest.json'));assert m['failed_replicates']==m['nonfinite_replicates']==0;assert m['workers']==16
  records=read_fasta(ds['blocks']);x.update(mode=mode,scheduler=scheduler,dataset=label,helper_jobs=m['record_helper_jobs'],worker_cpu_ids=m['worker_cpu_ids'],outputs=[])
  for i in range(30):
   p=dest/f'replicate-{i:02}.psmc';ref=(Path('work/linear-equivalent/validation')/(label+'-batch')/p.name) if mode=='equivalent' else (Path('work/equivalent/validation')/(label+'-strict-batch')/p.name)
   compare_output(ref.read_bytes(),p.read_bytes());indices,draws=draw_bootstrap(records,ds['samples'][i]['seed']);assert indices==m['replicates'][i]['source_indices']
   actual=[json.loads(l) for l in (dest/f'replicate-{i:02}.draws.jsonl').read_text().splitlines()];assert actual[:-1]==[dict(event='bootstrap_draw',draw=j,**d) for j,d in enumerate(draws)]
   x['outputs'].append(dict(path=str(p),sha256=sha256(p)))
  save(report,r);return x
 if a.stage=='validation':
  for label,mode in [('hg001','equivalent'),('hg002','equivalent'),('hg001','strict')]:batch(label,mode,'shared',f'{label}-{mode}')
  for mode in ['strict','equivalent']:
   ds=c['datasets']['hg001'];outputs=[]
   for workers in [1,16]:outputs.append(run([binary,'--mode',mode,'--record-workers',str(workers),'--seed','42',*ARGS,ds['blocks']],f'single-{mode}-{workers}')['output'])
   compare_output(*(Path(p).read_bytes() for p in outputs))
  # Small records exercise both cache policies, task-order reversal and one worker.
  for mode in ['strict','equivalent']:
   outputs=[]
   for workers,cache,order in [(1,'on','forward'),(4,'off','reverse'),(4,'on','forward')]:
    dest=raw/f'synthetic-{mode}-{workers}-{cache}';run([binary,'bootstrap','--mode',mode,'--scheduler','shared','--workers',str(workers),'--cache',cache,'--task-order',order,'--replicates','8','--seed','42','--output-dir',str(dest),'-p','2+2+2','-N','3','-I','0','tests/fixtures/repeated.psmcfa'],dest.name+'-time');outputs.append(dest)
   for i in range(8):
    ref=(outputs[0]/f'replicate-{i:02}.psmc').read_bytes()
    for d in outputs[1:]:compare_output(ref,(d/f'replicate-{i:02}.psmc').read_bytes())
 elif a.stage=='screen':
  for mode in (['equivalent','strict'] if a.screen_mode=='both' else [a.screen_mode]):
   for sched in ['fit','shared']:batch('hg001',mode,sched,f'{mode}-{sched}')
 else:
  validation=json.load(open('bench/shared-records-'+(a.variant+'-' if a.variant else '')+'validation.json'));assert validation['status']=='completed' and validation['binary_sha256']==r['binary_sha256']
  for mode in ['equivalent','strict']:
   for rep in range(4):
    for scheduler in (['fit','shared'] if rep%2==0 else ['shared','fit']):
     x=batch('hg001',mode,scheduler,f'{mode}-{scheduler}-{rep}');x['repeat']=rep;save(report,r)
  r['summary']={}
  for mode in ['equivalent','strict']:
   m={sched:{k:statistics.median(x[k] for x in r['runs'] if x['mode']==mode and x['scheduler']==sched and x['repeat']>0) for k in ['wall_seconds','cpu_seconds','peak_rss_kib','helper_jobs']} for sched in ['fit','shared']}
   reduction=1-m['shared']['wall_seconds']/m['fit']['wall_seconds'];wins=sum(next(x for x in r['runs'] if x['mode']==mode and x['scheduler']=='shared' and x['repeat']==i)['wall_seconds']<next(x for x in r['runs'] if x['mode']==mode and x['scheduler']=='fit' and x['repeat']==i)['wall_seconds'] for i in [1,2,3])
   r['summary'][mode]=dict(medians=m,wall_reduction=reduction,faster_pairs=wins,improvement_gate=reduction>=.05 and wins>=2,nonregression_gate=reduction>=-.05)
 assert sha256(binary)==r['binary_sha256'];r['status']='completed';save(report,r)
if __name__=='__main__':main()
