"""Fresh full-batch screens and fixed acceptance pairs against installed v0.4.1."""
import argparse,json,os,statistics
from pathlib import Path
from common import ROOT,save,sha256,timed_run,read_fasta,draw_bootstrap
from phase2_common import clean_env
from phase1_differential import compare_output

def main():
    os.chdir(ROOT);p=argparse.ArgumentParser();p.add_argument('phase',choices=['probe','screen','accept']);p.add_argument('--candidate');args=p.parse_args()
    raw=Path('work/relook')/('batches-'+args.phase);raw.mkdir()
    data=json.load(open('bench/hg-input.json'));canonical=json.load(open('bench/hg-benchmark.json'))['canonical_outputs'];records=read_fasta(data['blocks'])
    variants=json.load(open('bench/relook-counts.json'))['variants']
    if args.phase=='probe':
        binary='work/relook/probe/source/target/release/psmc-rs'
        assert sha256(binary)==json.load(open('bench/relook-probe.json'))['binary_sha256']
        jobs=[('diagnostic',binary,0)]
    elif args.phase=='screen':
        jobs=[('installed',variants['installed']['binary'],0)]+[(k,variants[k]['binary'],0) for k in ['uniform16','uniform64','uniformwide']]+[('installed',variants['installed']['binary'],1)]
    else:
        assert args.candidate
        jobs=[]
        for rep in range(4):
            for label in (['baseline','candidate'] if rep%2==0 else ['candidate','baseline']):
                jobs.append((label,variants['installed']['binary'] if label=='baseline' else args.candidate,rep))
    r=dict(status='running',runner_sha256=sha256(__file__),phase=args.phase,input_sha256=sha256(data['blocks']),runs=[],
           protocol='Screen: each candidate once between two installed controls. Acceptance: one warmup each, three alternating pairs; >=5% median elapsed reduction, lower median CPU, >=2/3 faster pairs. Diagnostic timings are not speed claims.')
    report='bench/relook-batches-'+args.phase+'.json'
    for label,binary,rep in jobs:
        out=raw/f'{label}-{rep}'
        cmd=['taskset','-c','0-15',binary,'bootstrap','--backend','cpu','--workers','16','--memory-mib','16384','--replicates','30','--seed',str(data['seed']),'--output-dir',str(out),'-p','4+25*2+4+6','-N','30','-t','15','-r','5','-I','0',data['blocks']]
        digest=sha256(binary);run=timed_run(cmd,ROOT/raw/f'{label}-{rep}-time',env=clean_env(),timeout=1800);assert run['exit_code']==0 and sha256(binary)==digest
        manifest=json.loads((out/'manifest.json').read_text());assert manifest['failed_replicates']==manifest['nonfinite_replicates']==0
        for i,c in enumerate(canonical):
            assert sha256(c['path'])==c['sha256'];compare_output(Path(c['path']).read_bytes(),(out/f'replicate-{i:02}.psmc').read_bytes())
            selected,draws=draw_bootstrap(records,data['seed']+i);assert manifest['replicates'][i]['source_indices']==selected
            actual=[json.loads(line) for line in (out/f'replicate-{i:02}.draws.jsonl').read_text().splitlines()]
            assert actual[:-1]==[dict(event='bootstrap_draw',draw=j,**d) for j,d in enumerate(draws)]
        run.update(label=label,repeat=rep,binary_sha256=digest,cpu_seconds=run['user_seconds']+run['system_seconds'],exact_outputs=30,manifest=str(out/'manifest.json'))
        if args.phase=='probe':
            rows=[json.loads(line[7:]) for line in (raw/f'{label}-{rep}-time.stderr').read_text().splitlines() if line.startswith('RELOOK ')]
            assert rows;run['diagnostic_rows']=rows;run['diagnostic_totals']={key:sum(row[key] for row in rows) for key in rows[0]}
        r['runs'].append(run);save(report,r);print(args.phase,label,rep,run['wall_seconds'],flush=True)
    if args.phase=='accept':
        r['summary']={label:{key:statistics.median(x[key] for x in r['runs'] if x['label']==label and x['repeat']>0) for key in ['wall_seconds','cpu_seconds','peak_rss_kib']} for label in ['baseline','candidate']}
        r['wall_reduction']=1-r['summary']['candidate']['wall_seconds']/r['summary']['baseline']['wall_seconds']
        r['cpu_reduction']=1-r['summary']['candidate']['cpu_seconds']/r['summary']['baseline']['cpu_seconds']
        r['faster_pairs']=sum(next(x for x in r['runs'] if x['label']=='candidate' and x['repeat']==rep)['wall_seconds']<next(x for x in r['runs'] if x['label']=='baseline' and x['repeat']==rep)['wall_seconds'] for rep in [1,2,3])
        r['performance_gate']=r['wall_reduction']>=.05 and r['cpu_reduction']>0 and r['faster_pairs']>=2
    r['status']='passed_exactness';save(report,r)
if __name__=='__main__':main()
