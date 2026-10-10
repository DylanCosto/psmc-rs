#!/usr/bin/env python3
"""Fixed warmup and three alternating 30-fit pairs, after correctness jobs finish."""
import json,os,statistics,subprocess
from pathlib import Path
from common import ROOT,save,sha256,timed_run,read_fasta,draw_bootstrap
from phase2_common import clean_env
from equivalent_c_baseline import ARGS
from phase1_differential import compare_output

def main():
    os.chdir(ROOT)
    # Prevent timings overlapping this campaign's long-running validation jobs.
    assert json.load(open('bench/equivalent-c-baseline.json'))['status']=='completed'
    assert json.load(open('bench/equivalent-validation.json'))['status']=='completed'
    assert json.load(open('bench/equivalent-strict-regression.json'))['status']!='running'
    raw=Path('work/equivalent/performance');raw.mkdir()
    # Only tests and API documentation were added since the validation build. Rebuild and verify that executable machine code is unchanged.
    with open('work/equivalent/tests-release-final.log','w') as log:
        subprocess.run(['cargo','test','--release','--locked','--offline','--workspace'],stdout=log,stderr=subprocess.STDOUT,check=True)
    subprocess.run(['cargo','build','--release','--locked','--offline','--bins','--examples'],check=True)
    binary='target/release/psmc-rs';digest=sha256(binary)
    for label,path in [('validation','work/equivalent/psmc-rs-validation'),('final',binary)]:
        before=sha256(path)
        subprocess.run(['objcopy','--dump-section',f'.text={raw}/{label}.text',path,str(raw/f'{label}-verification-copy.elf')],check=True)
        assert sha256(path)==before, 'verifier changed its input'
    assert (raw/'validation.text').read_bytes()==(raw/'final.text').read_bytes(), 'production machine code changed; revalidate before timing'

    data=json.load(open('bench/hg-input.json')); records=read_fasta(data['blocks'])
    r=dict(status='running',binary_sha256=digest,runner_sha256=sha256(__file__),input_sha256=sha256(data['blocks']),runs=[],protocol='One warmup per mode, three alternating measured pairs, same binary and 16 workers. >=5% less median wall time, >=2/3 wins; no optional repetitions.')
    report='bench/equivalent-performance.json'
    r['control_runs']=[]
    def old_control(label):
        out=raw/f'v041-{label}'
        cmd=['taskset','-c','0-15','bin/psmc-rs-v0.4.1','bootstrap','--backend','cpu','--workers','16','--memory-mib','16384','--replicates','30','--seed',str(data['seed']),'--output-dir',str(out),*ARGS,data['blocks']]
        run=timed_run(cmd,ROOT/raw/f'v041-{label}-time',env=clean_env(),timeout=1800);assert run['exit_code']==0
        for i in range(30):
            compare_output((Path('work/equivalent/validation/hg001-strict-batch')/f'replicate-{i:02}.psmc').read_bytes(),(out/f'replicate-{i:02}.psmc').read_bytes())
        run.update(label=label,binary_sha256=sha256('bin/psmc-rs-v0.4.1'),cpu_seconds=run['user_seconds']+run['system_seconds'],outputs=[dict(path=str(out/f'replicate-{i:02}.psmc'),sha256=sha256(out/f'replicate-{i:02}.psmc')) for i in range(30)])
        r['control_runs'].append(run);save(report,r);print('v041',label,run['wall_seconds'],flush=True)
    old_control('before')
    for rep in range(4):
        for mode in (['strict','equivalent'] if rep%2==0 else ['equivalent','strict']):
            out=raw/f'{mode}-{rep}'
            cmd=['taskset','-c','0-15',binary,'bootstrap','--mode',mode,'--workers','16','--memory-mib','16384','--replicates','30','--seed',str(data['seed']),'--output-dir',str(out),*ARGS,data['blocks']]
            run=timed_run(cmd,ROOT/raw/f'{mode}-{rep}-time',env=clean_env(),timeout=1800)
            assert run['exit_code']==0 and sha256(binary)==digest
            manifest=json.load(open(out/'manifest.json'));assert manifest['failed_replicates']==manifest['nonfinite_replicates']==0
            counters=[];outputs=[]
            for i in range(30):
                p=out/f'replicate-{i:02}.psmc';canonical=Path('work/equivalent/validation')/f'hg001-{mode}-batch'/p.name
                assert p.read_bytes()==canonical.read_bytes()
                indices,draws=draw_bootstrap(records,data['seed']+i);assert manifest['replicates'][i]['source_indices']==indices
                actual=[json.loads(line) for line in (out/f'replicate-{i:02}.draws.jsonl').read_text().splitlines()]
                assert actual[:-1]==[dict(event='bootstrap_draw',draw=j,**d) for j,d in enumerate(draws)]
                outputs.append(dict(path=str(p),sha256=sha256(p)))
                counters.append(json.load(open(out/f'replicate-{i:02}.stats.json')))
            run.update(mode=mode,repeat=rep,cpu_seconds=run['user_seconds']+run['system_seconds'],structured_fallbacks=sum(c['structured_fallbacks'] for c in counters),model_updates=sum(c['model_updates'] for c in counters),outputs=outputs)
            r['runs'].append(run);save(report,r);print(mode,rep,run['wall_seconds'],flush=True)
    old_control('after')
    r['summary']={mode:{k:statistics.median(run[k] for run in r['runs'] if run['mode']==mode and run['repeat']>0) for k in ['wall_seconds','cpu_seconds','peak_rss_kib']} for mode in ['strict','equivalent']}
    r['strict_vs_v041_control_ratio']=r['summary']['strict']['wall_seconds']/statistics.mean(x['wall_seconds'] for x in r['control_runs'])
    r['speedup']=r['summary']['strict']['wall_seconds']/r['summary']['equivalent']['wall_seconds']
    r['wall_reduction']=1-1/r['speedup'];r['cpu_reduction']=1-r['summary']['equivalent']['cpu_seconds']/r['summary']['strict']['cpu_seconds']
    r['faster_pairs']=sum(next(x for x in r['runs'] if x['mode']=='equivalent' and x['repeat']==rep)['wall_seconds']<next(x for x in r['runs'] if x['mode']=='strict' and x['repeat']==rep)['wall_seconds'] for rep in [1,2,3])
    r['performance_gate']=r['wall_reduction']>=.05 and r['faster_pairs']>=2
    r['status']='completed';save(report,r)
if __name__=='__main__':main()
