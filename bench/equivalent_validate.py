#!/usr/bin/env python3
"""Full fits and scheduling controls for the opt-in structured mode."""
import json, os, subprocess
from pathlib import Path
from common import ROOT,save,sha256,timed_run,read_fasta,draw_bootstrap
from phase2_common import clean_env
from phase1_differential import compare_output
from equivalent_c_baseline import ARGS

def main():
    os.chdir(ROOT);raw=Path('work/equivalent/validation');raw.mkdir()
    binary='target/release/psmc-rs';digest=sha256(binary)
    inputs=json.load(open('bench/equivalent-c-baseline.json'))['datasets']
    r=dict(status='running',binary=binary,binary_sha256=digest,runner_sha256=sha256(__file__),runs=[],timing='Diagnostic only; C validation may run concurrently. Performance measured separately.')
    report='bench/equivalent-validation.json'
    for label,data in inputs.items():
        for mode in ['strict','equivalent']:
            stats=raw/f'{label}-{mode}.stats.json'
            cmd=[binary,'--mode',mode,'--stats',str(stats),*ARGS,data['original']]
            run=timed_run(cmd,ROOT/raw/f'{label}-{mode}',env=clean_env(),timeout=3600)
            run.update(dataset=label,mode=mode,kind='original',stats=json.load(open(stats)));r['runs'].append(run);save(report,r)
            assert run['exit_code']==0
            if mode=='strict':
                oracle='bench/hg/pilot/vanilla.psmc' if label=='hg001' else 'work/cpu-next/large/vanilla.psmc'
                run['strict_comparison']=compare_output(Path(oracle).read_bytes(),Path(run['output']).read_bytes())
            print(label,mode,'original',round(run['wall_seconds'],2),flush=True)
            dest=raw/f'{label}-{mode}-batch'
            cmd=[binary,'bootstrap','--mode',mode,'--workers','16','--memory-mib','16384','--replicates','30','--seed',str(data['samples'][0]['seed']),'--output-dir',str(dest),*ARGS,data['blocks']]
            run=timed_run(cmd,ROOT/raw/f'{label}-{mode}-batch-time',env=clean_env(),timeout=3600)
            manifest=json.load(open(dest/'manifest.json'));assert run['exit_code']==0 and manifest['failed_replicates']==0
            assert manifest['mode']==mode
            run.update(dataset=label,mode=mode,kind='bootstrap',manifest=str(dest/'manifest.json'),outputs=[])
            records=read_fasta(data['blocks'])
            for i in range(30):
                output=dest/f'replicate-{i:02}.psmc';stats=json.load(open(dest/f'replicate-{i:02}.stats.json'))
                indices,draws=draw_bootstrap(records,data['samples'][i]['seed'])
                assert manifest['replicates'][i]['source_indices']==indices==data['samples'][i]['indices']
                actual=[json.loads(line) for line in (dest/f'replicate-{i:02}.draws.jsonl').read_text().splitlines()]
                assert actual[:-1]==[dict(event='bootstrap_draw',draw=j,**d) for j,d in enumerate(draws)]
                run['outputs'].append(dict(index=i,path=str(output),sha256=sha256(output),stats=stats))
            r['runs'].append(run);save(report,r);print(label,mode,'batch',round(run['wall_seconds'],2),flush=True)
    # Equivalent scheduling and cache controls on a small repeated/masked fixture.
    r['scheduler']=[]
    for workers,order,cache in [(1,'forward','on'),(4,'reverse','on'),(1,'forward','off')]:
        dest=raw/f'scheduler-{workers}-{order}-{cache}'
        cmd=[binary,'bootstrap','--mode','equivalent','--workers',str(workers),'--task-order',order,'--cache',cache,'--replicates','8','--seed','1234','--output-dir',str(dest),'-p','2+2+2','-N','5','-t','5','-I','0','tests/fixtures/repeated.psmcfa']
        result=timed_run(cmd,ROOT/raw/(dest.name+'-time'),env=clean_env(),timeout=300);assert result['exit_code']==0
        if r['scheduler']:
            baseline=Path(r['scheduler'][0]['directory'])
            for i in range(8):assert (baseline/f'replicate-{i:02}.psmc').read_bytes()==(dest/f'replicate-{i:02}.psmc').read_bytes()
        r['scheduler'].append(dict(directory=str(dest),result=result))
    assert sha256(binary)==digest
    r['status']='completed';save(report,r)
if __name__=='__main__':main()
