#!/usr/bin/env python3
"""Separate, immutable-evidence screen/validation/acceptance for lockstep SIMD."""
import argparse,json,os,statistics
from pathlib import Path
from common import ROOT,save,sha256,timed_run,read_fasta,draw_bootstrap
from phase2_common import clean_env
from phase1_differential import compare_output
from equivalent_c_baseline import ARGS

def main():
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['screen','validation','performance']);ap.add_argument('--variant',default='bounded');a=ap.parse_args();os.chdir(ROOT)
    raw=Path('work/equivalent-followup')/(a.variant+'-'+a.stage);raw.mkdir()
    report=f'bench/equivalent-followup-{a.variant}-{a.stage}.json'
    inputs=json.load(open('bench/equivalent-c-baseline.json'))['datasets']
    binaries={'baseline':'bin/psmc-rs-v0.5.0','candidate':'target/release/psmc-rs'}
    r=dict(status='running',stage=a.stage,runner_sha256=sha256(__file__),base_commit='f191674',binaries={k:dict(path=p,sha256=sha256(p)) for k,p in binaries.items()},runs=[])
    def batch(which,label,tag,mode='equivalent'):
        data=inputs[label];out=raw/tag;binary=binaries[which]
        cmd=['taskset','-c','0-15',binary,'bootstrap','--mode',mode,'--workers','16','--memory-mib','16384','--replicates','30','--seed',str(data['samples'][0]['seed']),'--output-dir',str(out),*ARGS,data['blocks']]
        run=timed_run(cmd,ROOT/raw/(tag+'-time'),env=clean_env(),timeout=3600);assert run['exit_code']==0
        manifest=json.load(open(out/'manifest.json'));assert manifest['failed_replicates']==manifest['nonfinite_replicates']==0
        assert manifest['workers']==16
        run.update(which=which,dataset=label,tag=tag,mode=mode,cpu_seconds=run['user_seconds']+run['system_seconds'],outputs=[])
        records=read_fasta(data['blocks'])
        for i in range(30):
            p=out/f'replicate-{i:02}.psmc';ref=Path('work/equivalent/validation')/f'{label}-{mode}-batch'/p.name
            compare_output(ref.read_bytes(),p.read_bytes())
            indices,draws=draw_bootstrap(records,data['samples'][i]['seed']);assert indices==manifest['replicates'][i]['source_indices']
            actual=[json.loads(line) for line in (out/f'replicate-{i:02}.draws.jsonl').read_text().splitlines()]
            assert actual[:-1]==[dict(event='bootstrap_draw',draw=j,**d) for j,d in enumerate(draws)]
            run['outputs'].append(dict(path=str(p),sha256=sha256(p)))
        assert sha256(binary)==r['binaries'][which]['sha256']
        r['runs'].append(run);save(report,r);print(tag,round(run['wall_seconds'],3),flush=True)
        return run
    if a.stage=='screen':
        b=batch('baseline','hg001','baseline');c=batch('candidate','hg001','candidate')
        r['screen_reduction']=1-c['wall_seconds']/b['wall_seconds'];r['screen_pass']=r['screen_reduction']>=.05
    elif a.stage=='validation':
        for label,data in inputs.items():
            for mode in ['equivalent','strict']:
                run=timed_run([binaries['candidate'],'--mode',mode,*ARGS,data['original']],ROOT/raw/f'{label}-{mode}',env=clean_env(),timeout=3600)
                assert run['exit_code']==0
                compare_output((Path('work/equivalent/validation')/f'{label}-{mode}.psmc').read_bytes(),Path(run['output']).read_bytes())
                run.update(dataset=label,mode=mode,kind='original');r['runs'].append(run);save(report,r);print(label,mode,'original',flush=True)
            batch('candidate',label,label+'-equivalent')
        # Strict complete human batch is checked on HG001; exact golden fixtures
        # and original HG002 cover the refactored common message/count boundary.
        batch('candidate','hg001','hg001-strict','strict')
    else:
        assert json.load(open(f'bench/equivalent-followup-{a.variant}-screen.json'))['screen_pass']
        validation=json.load(open(f'bench/equivalent-followup-{a.variant}-validation.json'))
        assert validation['status']=='completed'
        assert validation['binaries']['candidate']['sha256']==r['binaries']['candidate']['sha256']
        regression=json.load(open('bench/equivalent-followup-strict-regression.json'))
        assert regression['status']!='running'
        passed=0;obsolete=0
        for backend,entry in regression['backend_reports'].items():
            for case in json.load(open(entry['report']))['cases']:
                if case['status']=='passed':passed+=1
                else:
                    assert backend in ['cpu','scalar'] and case['name']=='reject_equivalent_mode',case
                    obsolete+=1
        assert (passed,obsolete)==(338,2)
        r['protocol']='One warmup and three alternating pairs; 30 HG001 bootstraps, 16 workers. >=5% median wall reduction and >=2/3 faster pairs.'
        r['strict_controls']=[batch('baseline','hg001','strict-baseline','strict')]
        r['runs'].pop()
        for rep in range(4):
            for which in (['baseline','candidate'] if rep%2==0 else ['candidate','baseline']):
                run=batch(which,'hg001',f'{which}-{rep}');run['repeat']=rep;save(report,r)
        r['strict_controls'].append(batch('candidate','hg001','strict-candidate','strict'))
        r['runs'].pop()
        r['summary']={w:{k:statistics.median(x[k] for x in r['runs'] if x['which']==w and x['repeat']>0) for k in ['wall_seconds','cpu_seconds','peak_rss_kib']} for w in binaries}
        r['wall_reduction']=1-r['summary']['candidate']['wall_seconds']/r['summary']['baseline']['wall_seconds']
        r['faster_pairs']=sum(next(x for x in r['runs'] if x['which']=='candidate' and x['repeat']==rep)['wall_seconds']<next(x for x in r['runs'] if x['which']=='baseline' and x['repeat']==rep)['wall_seconds'] for rep in [1,2,3])
        r['performance_gate']=r['wall_reduction']>=.05 and r['faster_pairs']>=2
    r['status']='completed';save(report,r)
if __name__=='__main__':main()
