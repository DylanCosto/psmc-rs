#!/usr/bin/env python3
"""Collect equivalent fallback counters; require exact replay of every primary fit."""
import argparse,json,subprocess,os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import known_truth as p

def main():
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--panel',type=Path,required=True);a=a.parse_args();root=a.panel.resolve()
 dirs=sorted(x for x in root.iterdir() if (x/'equivalent.out').exists())
 assert len(dirs)==30,'wait for all primary fits before collecting diagnostic replays'
 out=root.parent/'equivalent-stats';out.mkdir(exist_ok=False)
 def run(folder):
  name=folder.name;stats=out/f'{name}.json';output=out/f'{name}.psmc'
  cmd=[str(root/'binaries/rust'),'--mode','equivalent','--record-workers','1','--stats',str(stats),*p.FIT,str(folder/'input.psmcfa')]
  with output.open('w') as f,(out/f'{name}.stderr').open('w') as e:subprocess.run(cmd,stdout=f,stderr=e,check=True,timeout=600)
  assert output.read_bytes()==(folder/'equivalent.out').read_bytes(),name
  s=json.loads(stats.read_text());return {'case':name,'model_updates':s['model_updates'],'structured_fallbacks':s['structured_fallbacks'],'output_exact':True,'stats_sha256':p.sha(stats)}
 # Accuracy-only replays: eight fits on this machine's allowed P-core threads.
 allowed=os.sched_getaffinity(0);os.sched_setaffinity(0,allowed & set(range(12)) or allowed)
 results=[]
 with ThreadPoolExecutor(max_workers=8) as pool:
  for future in as_completed([pool.submit(run,d) for d in dirs]):
   result=future.result();results.append(result);print(result['case'],result['structured_fallbacks'],flush=True)
 results.sort(key=lambda r:r['case']);updates=sum(r['model_updates'] for r in results);fallbacks=sum(r['structured_fallbacks'] for r in results)
 report={'scope':'30 additional equivalent-mode instrumented replays; each matches its frozen uninstrumented primary output exactly. No performance claim.','model_updates':updates,'structured_fallbacks':fallbacks,'fallback_fraction':fallbacks/updates,'cases':results}
 p.save(out/'report.json',report);print(json.dumps({k:v for k,v in report.items() if k!='cases'},indent=2))
if __name__=='__main__':main()
