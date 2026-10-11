#!/usr/bin/env python3
"""Fixed 200 Mb accuracy panel with prospectively defined time bands/events."""
import argparse
from bisect import bisect_right
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib,json,math,shlex,shutil,statistics,subprocess
from pathlib import Path
import known_truth as pilot
ROOT=pilot.ROOT
LENGTH,RECORDS,REPLICATES=10_000_000,20,10
HISTORIES={'constant':[(0,10000)],'bottleneck':[(0,10000),(10000,2000),(30000,10000)],'expansion':[(0,20000),(20000,10000)]}
BANDS={'recent':(1000,5000),'primary_early':(5000,20000),'primary_late':(20000,80000),'ancient':(80000,200000)}

def grid(a,b): return [a*math.exp(math.log(b/a)*i/128) for i in range(128)]
def at(params,t):
 i=max(0,bisect_right(params['group_starts_generations'],t)-1)
 return math.log(params['n0']*params['lambdas'][i])
def truth(history,t): return math.log(history[max(0,bisect_right([x[0] for x in history],t)-1)][1])
def curve_metrics(params,history,a,b):
 times=grid(a,b); true=[truth(history,t) for t in times]
 curves={m:[at(p,t) for t in times] for m,p in params.items()}
 differences=[abs(s-e) for s,e in zip(curves['strict'],curves['equivalent'])]
 return {'rmse':{m:pilot.rmse(c,true) for m,c in curves.items()},'mode_curve_rmse':pilot.rmse(curves['strict'],curves['equivalent']),'mode_curve_max':max(differences),'log_curves':curves,'truth_log_curve':true}
def event_ratio(params,history):
 if history=='constant':return None
 a,b,c,d=(12000,24000,50000,80000) if history=='bottleneck' else (5000,10000,40000,60000)
 return math.exp(statistics.mean(at(params,t) for t in grid(a,b))-statistics.mean(at(params,t) for t in grid(c,d)))

def case(name,index,out,binaries):
 folder=out/f'{name}-{index:02}';folder.mkdir()
 try:
  hist=HISTORIES[name];history_file=folder/'truth.history'
  history_file.write_text('T 0.1\nR 0.02\n'+''.join(f'H {t/20000:.12g} {n/10000:.12g}\n' for t,n in hist))
  emitted=subprocess.check_output(['perl',str(ROOT/'work/vanilla/utils/history2ms.pl'),'-L',str(LENGTH),'-r',str(RECORDS),'-u',str(pilot.MU),str(history_file)],text=True).strip()
  args=shlex.split(emitted)
  assert args[0]=='msHOT-lite' and args.count('-l')==1
  j=list(HISTORIES).index(name)*10+index;seeds=[11001+73*j,22009+137*j,33007+193*j]
  command=[str(binaries['ms']),*[x for x in args[1:] if x!='-l'],'-p','12','-seeds',*map(str,seeds)]
  simulation=pilot.run(command,folder/'simulation')
  encoded=folder/'input.psmcfa';encoded.write_text(pilot.convert_ms((folder/'simulation.out').read_text(),length=LENGTH,bin_size=100,expected=RECORDS))
  runs, texts, params,full_curves={},{},{},{}
  for mode in ['c','strict','equivalent']:
   command=[str(binaries['c']),*pilot.FIT] if mode=='c' else [str(binaries['rust']),'--mode',mode,'--record-workers','1',*pilot.FIT]
   runs[mode]=pilot.run([*command,str(encoded)],folder/mode)
   texts[mode]=(folder/f'{mode}.out').read_text()
   full_curves[mode],params[mode]=pilot.curve(texts[mode])
  true=[truth(hist,t) for t in pilot.GRID]
  bands={band:curve_metrics(params,hist,*limits) for band,limits in BANDS.items()}
  ratios={mode:event_ratio(p,name) for mode,p in params.items()}
  record={'history':name,'index':index,'status':'complete','history2ms_command':emitted,'seeds':seeds,'simulation':simulation,'input_sha256':pilot.sha(encoded),'runs':runs,'strict_c_exact':pilot.numerical(texts['strict'])==pilot.numerical(texts['c']),'parameters':params,'bands':bands,'event_ratios':ratios,'full_grid_rmse':{mode:pilot.rmse(curve,true) for mode,curve in full_curves.items()}}
  if any(b['mode_curve_rmse']>.01 for b in bands.values()):
   cmd=[str(binaries['ridge']),str(encoded),str(folder/'strict.out'),str(folder/'equivalent.out')]
   with (folder/'ridge.jsonl').open('w') as f:
    subprocess.run(cmd,stdout=f,stderr=subprocess.PIPE,check=True,timeout=600)
   record['ridge']=[json.loads(line) for line in (folder/'ridge.jsonl').read_text().splitlines()]
  else:record['ridge']=None
 except Exception as e:record={'history':name,'index':index,'status':'failed','error':str(e)}
 pilot.save(folder/'result.json',record)
 return record

def summarize(records):
 summaries={}
 for name in HISTORIES:
  fits=[r for r in records if r['history']==name and r['status']=='complete']
  if len(fits)!=10:
   summaries[name]={'passed':False,'complete':len(fits),'planned':10};continue
  bands={}
  for band in BANDS:
   samples=[r['bands'][band] for r in fits]
   delta=[r['rmse']['equivalent']-r['rmse']['strict'] for r in samples]
   upper=statistics.mean(delta)+1.833112933*statistics.stdev(delta)/math.sqrt(10)
   baseline=math.sqrt(statistics.mean(r['rmse']['strict']**2 for r in samples))
   difference=math.sqrt(statistics.mean(r['mode_curve_rmse']**2 for r in samples))
   means={m:statistics.mean(r['rmse'][m] for r in samples) for m in ['c','strict','equivalent']}
   bands[band]={'primary':band.startswith('primary'),'mean_rmse':means,'pooled_truth_rmse':baseline,'pooled_mode_difference':difference,'mode_difference_fraction':difference/baseline,'upper_paired_error_difference':upper,'relative_checks_passed':upper<.05 and difference<=.1*baseline,'absolute_checks_passed':all(means[m]<=.5 for m in ['strict','equivalent'])}
  events={m:statistics.median(r['event_ratios'][m] for r in fits) for m in ['strict','equivalent']} if name!='constant' else None
  event_pass=events is None or all(x<.75 if name=='bottleneck' else x>1.25 for x in events.values())
  exact=all(r['strict_c_exact'] for r in fits)
  summaries[name]={'complete':10,'bands':bands,'event_median_ratios':events,'event_passed':event_pass,'strict_c_exact':exact,'passed':exact and event_pass and all(b['relative_checks_passed'] and b['absolute_checks_passed'] for b in bands.values() if b['primary'])}
 return summaries

def relative(x):
 if isinstance(x,str):return x.replace(str(ROOT)+'/', '')
 if isinstance(x,list):return [relative(v) for v in x]
 if isinstance(x,dict):return {k:relative(v) for k,v in x.items()}
 return x

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--jobs',type=int,default=8);a=p.parse_args()
 if not 1<=a.jobs<=8:raise ValueError('jobs must be 1..8')
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);refs=out/'binaries';refs.mkdir()
 source={'ms':ROOT/'work/qualification/msdir/ms','c':ROOT/'work/vanilla/psmc','rust':ROOT/'target/release/psmc-rs','ridge':ROOT/'target/release/examples/equivalent_ridge'}
 binaries={}
 for name,path in source.items():binaries[name]=refs/name;shutil.copy2(path,binaries[name])
 meta={'protocol_sha256':pilot.sha(ROOT/'docs/known-truth-200mb-protocol.md'),'runner_sha256':pilot.sha(Path(__file__)),'shared_helper_sha256':pilot.sha(ROOT/'bench/known_truth.py'),'binary_hashes':{name:pilot.sha(path) for name,path in binaries.items()},'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'working_diff_sha256':hashlib.sha256(subprocess.check_output(['git','diff'],cwd=ROOT)).hexdigest(),'histories':HISTORIES,'bands':BANDS,'length':LENGTH,'records':RECORDS,'replicates':REPLICATES,'fit_args':pilot.FIT,'jobs':a.jobs}
 pilot.save(out/'frozen.json',meta)
 results=[]
 with ThreadPoolExecutor(max_workers=a.jobs) as pool:
  futures=[pool.submit(case,name,i,out,binaries) for name in HISTORIES for i in range(10)]
  for future in as_completed(futures):
   result=future.result();results.append(result);print(result['history'],result['index'],result['status'],result.get('error',''),flush=True)
 results.sort(key=lambda r:(r['history'],r['index']));summary=summarize(results)
 report=relative({'metadata':meta,'summary':summary,'passed':all(s['passed'] for s in summary.values()),'cases':results})
 pilot.save(out/'report.json',report);print(json.dumps(summary,indent=2),flush=True)
 raise SystemExit(0 if report['passed'] else 1)
if __name__=='__main__':main()
