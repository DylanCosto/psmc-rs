"""Fixed acceptance pairs for an explicitly chosen frozen candidate."""
import os,json,argparse,statistics
from pathlib import Path
from common import ROOT,save,sha256,timed_run,read_fasta,draw_bootstrap
from phase2_common import clean_env
from phase1_differential import compare_output

def main():
    os.chdir(ROOT);p=argparse.ArgumentParser();p.add_argument('--candidate',required=True);p.add_argument('--backend',default='cpu');p.add_argument('--label',required=True);p.add_argument('--workers',type=int,default=16);p.add_argument('--affinity',default='0-15');p.add_argument('--tile',default='16384');args=p.parse_args()
    raw=Path('work/exhaust')/args.label;raw.mkdir()
    data=json.load(open('bench/hg-input.json'));canonical=json.load(open('bench/hg-benchmark.json'))['canonical_outputs'];records=read_fasta(data['blocks'])
    binaries={'baseline':'bin/psmc-rs-v0.3.3','candidate':args.candidate};hashes={k:sha256(v) for k,v in binaries.items()}
    r=dict(status='running',runner_sha256=sha256(__file__),binaries={k:dict(path=v,sha256=hashes[k]) for k,v in binaries.items()},input_sha256=sha256(data['blocks']),options=vars(args),runs=[],protocol='One warmup per configuration, three alternating pairs. CPU >=2% wall reduction, lower median CPU, >=2/3 faster pairs; GPU >=5% wall reduction vs CPU. No optional repeats.')
    for rep in range(4):
        for label in (['baseline','candidate'] if rep%2==0 else ['candidate','baseline']):
            assert sha256(binaries[label])==hashes[label]
            backend=args.backend if label=='candidate' else 'cpu';workers=args.workers if label=='candidate' else 16;affinity=args.affinity if label=='candidate' else '0-15'
            out=raw/f'{label}-{rep}'
            cmd=['taskset','-c',affinity,binaries[label],'bootstrap','--backend',backend,'--workers',str(workers),'--memory-mib','16384','--replicates','30','--seed',str(data['seed']),'--output-dir',str(out),'-p','4+25*2+4+6','-N','30','-t','15','-r','5','-I','0']
            if backend=='cuda':cmd+=['--cuda-tile-sites',args.tile,'--cuda-memory-mib','1024']
            cmd+=[data['blocks']]
            env={**clean_env(),'PSMC_NVRTC_LIBRARY':json.load(open('bench/cuda-environment.json'))['nvrtc_path']}
            run=timed_run(cmd,ROOT/raw/f'{label}-{rep}-time',env=env,timeout=1800);assert run['exit_code']==0
            manifest=json.loads((out/'manifest.json').read_text());assert manifest['failed_replicates']==0 and manifest['nonfinite_replicates']==0
            for i,c in enumerate(canonical):
                assert sha256(c['path'])==c['sha256'];compare_output(Path(c['path']).read_bytes(),(out/f'replicate-{i:02}.psmc').read_bytes())
                selected,draws=draw_bootstrap(records,data['seed']+i);assert manifest['replicates'][i]['source_indices']==selected
                actual=[json.loads(line) for line in (out/f'replicate-{i:02}.draws.jsonl').read_text().splitlines()]
                assert actual[:-1]==[dict(event='bootstrap_draw',draw=j,**d) for j,d in enumerate(draws)]
            run.update(label=label,repeat=rep,exact_outputs=30,cpu_seconds=run['user_seconds']+run['system_seconds'],admitted_workers=manifest['workers']);r['runs'].append(run);save('bench/exhaust-'+args.label+'.json',r);print(args.label,label,rep,run['wall_seconds'],flush=True)
    r['summary']={label:{key:statistics.median(x[key] for x in r['runs'] if x['label']==label and x['repeat']>0) for key in ['wall_seconds','cpu_seconds','peak_rss_kib']} for label in binaries}
    r['faster_pairs']=sum(next(x for x in r['runs'] if x['label']=='candidate' and x['repeat']==rep)['wall_seconds']<next(x for x in r['runs'] if x['label']=='baseline' and x['repeat']==rep)['wall_seconds'] for rep in [1,2,3])
    r['wall_reduction']=1-r['summary']['candidate']['wall_seconds']/r['summary']['baseline']['wall_seconds'];r['cpu_reduction']=1-r['summary']['candidate']['cpu_seconds']/r['summary']['baseline']['cpu_seconds']
    r['performance_gate']=r['wall_reduction']>=(.05 if args.backend=='cuda' else .02) and r['faster_pairs']>=2 and (args.backend=='cuda' or r['cpu_reduction']>0)
    r['status']='passed_exactness';save('bench/exhaust-'+args.label+'.json',r);print(json.dumps(r['summary']),r['performance_gate'],flush=True)
if __name__=='__main__':main()
