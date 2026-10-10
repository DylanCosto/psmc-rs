#!/usr/bin/env python3
"""Complete the explicitly selected two-build comparison without rerunning controls."""
import concurrent.futures as cf,json,os,time
from pathlib import Path
from common import ROOT,save,sha256,timed_run
from phase2_common import clean_env
from equivalent_c_baseline import ARGS,RAW,REPORT

def main():
    os.chdir(ROOT);r=json.load(open(REPORT));r['completion_runner_sha256']=sha256(__file__)
    assert r['selected_builds']==['o2','fma']
    completed={(x['dataset'],x['build'],x['kind'],x.get('index')) for x in r['runs']}
    for label,data in r['datasets'].items():
        for name in r['selected_builds']:
            build=r['builds'][name];assert sha256(build['path'])==build['sha256']
            if (label,name,'original',None) not in completed:
                run=timed_run(['taskset','-c','0',build['path'],*ARGS,data['original']],ROOT/RAW/f'{label}-{name}-original',env=clean_env(),timeout=3600)
                run.update(dataset=label,build=name,kind='original');r['runs'].append(run);save(REPORT,r);print(label,name,'original',round(run['wall_seconds'],2),flush=True)
            pending=[s for s in data['samples'] if (label,name,'bootstrap',s['index']) not in completed]
            started=time.perf_counter()
            def fit(s):
                i=s['index'];run=timed_run([build['path'],*ARGS,s['path']],ROOT/RAW/f'{label}-{name}-{i:02}',env=clean_env(),timeout=3600)
                run.update(dataset=label,build=name,kind='bootstrap',index=i);return run
            with cf.ThreadPoolExecutor(max_workers=16) as pool:
                for run in pool.map(fit,pending):r['runs'].append(run);save(REPORT,r)
            if pending:print(label,name,'bootstrap',len(pending),round(time.perf_counter()-started,2),flush=True)
    assert len(r['runs'])==124
    r['status']='completed' if all(x['exit_code']==0 for x in r['runs']) else 'failed';save(REPORT,r)
if __name__=='__main__':main()
