"""Extended C fixtures, held-out chromosomes, and ordered scheduler gates."""
import os,json,subprocess,argparse
from pathlib import Path
from common import ROOT,save,sha256,timed_run
from phase2_common import clean_env
from phase1_differential import compare_output

def main():
    os.chdir(ROOT);p=argparse.ArgumentParser();p.add_argument('--candidate',required=True);args=p.parse_args()
    raw=Path('work/exhaust/validation');raw.mkdir();binary=args.candidate;digest=sha256(binary)
    r=dict(status='running',binary=binary,binary_sha256=digest,runner_sha256=sha256(__file__),extended=[],human=[],scheduler=[])
    for source in ['bench/cpu-campaign-fixtures.json','bench/cpu-campaign-hmm-fixtures.json']:
        previous=json.load(open(source));assert previous['status']=='passed'
        for c in previous['cases']:
            oracle=next(x for x in c['runs'] if x['label']=='vanilla');assert sha256(oracle['output'])==oracle['sha256'] and sha256(c['input'])==c['input_sha256']
            out=raw/(c['id']+'.psmc');cmd=[binary,'--backend','cpu','--seed','42','-o',str(out),*oracle['command'][3:]]
            result=subprocess.run(cmd,env=clean_env(),capture_output=True,timeout=600);(raw/(c['id']+'.stderr')).write_bytes(result.stderr);assert result.returncode==0
            comparison=compare_output(Path(oracle['output']).read_bytes(),out.read_bytes());r['extended'].append(dict(id=c['id'],command=cmd,input_sha256=c['input_sha256'],oracle=oracle['output'],oracle_sha256=oracle['sha256'],output=str(out),comparison=comparison,finite=c['finite']));save('bench/exhaust-validation.json',r)
    for label,inp,oracle in [('hg001','work/hg-input/NA12878_chr22.psmcfa','bench/hg/pilot/vanilla.psmc'),('hg002','work/cpu-next/hg002/HG002_GRCh38_chr1.psmcfa','work/cpu-next/large/vanilla.psmc')]:
        for rep in range(2):
            order=[('baseline','bin/psmc-rs-v0.3.3'),('candidate',binary)]
            if rep:order.reverse()
            for variant,path in order:
                cmd=['taskset','-c','0',path,'--backend','cpu','--seed','42','-p','4+25*2+4+6','-N','30','-t','15','-r','5','-I','0',inp]
                run=timed_run(cmd,ROOT/raw/f'{label}-{rep}-{variant}',env=clean_env(),timeout=1800);assert run['exit_code']==0
                comparison=compare_output(Path(oracle).read_bytes(),Path(run['output']).read_bytes());assert not run['nonfinite_records_beyond_initial_RI']
                run.update(label=label,repeat=rep,variant=variant,binary_sha256=sha256(path),input_sha256=sha256(inp),oracle=oracle,oracle_sha256=sha256(oracle),comparison=comparison);r['human'].append(run);save('bench/exhaust-validation.json',r);print(label,rep,variant,run['wall_seconds'],flush=True)
    for label,workers,reverse in [('forward',1,False),('reverse',16,True)]:
        out=raw/label;cmd=[binary,'bootstrap','--backend','cpu','--workers',str(workers),'--replicates','30','--seed','20261009','--memory-mib','2048','--output-dir',str(out),'-p','4+5*3+4','-N','30','-t','15','-r','4','-I','0','tests/fixtures/blocks.psmcfa']
        if reverse:cmd+=['--task-order','reverse']
        run=timed_run(cmd,ROOT/raw/(label+'-time'),env=clean_env(),timeout=600);assert run['exit_code']==0
        manifest=json.loads((out/'manifest.json').read_text());assert manifest['failed_replicates']==0
        if reverse:
            for i in range(30):compare_output((raw/'forward'/f'replicate-{i:02}.psmc').read_bytes(),(out/f'replicate-{i:02}.psmc').read_bytes())
        r['scheduler'].append(dict(label=label,run=run,manifest=manifest));save('bench/exhaust-validation.json',r)
    assert sha256(binary)==digest;r['status']='passed';save('bench/exhaust-validation.json',r)
if __name__=='__main__':main()
