"""Fixed complete 30-bootstrap CUDA/16-core CPU go/no-go protocol."""
import os,json,statistics,threading,subprocess,time
from pathlib import Path
from common import ROOT,save,sha256,timed_run,read_fasta,draw_bootstrap
from phase1_differential import compare_output

def main():
    os.chdir(ROOT);raw=Path('work/cuda/batches');raw.mkdir(exist_ok=True)
    env=dict(os.environ,PSMC_NVRTC_LIBRARY=json.load(open('bench/cuda-environment.json'))['nvrtc_path'])
    binaries={'cpu':'bin/psmc-rs-v0.3.3','cuda':'work/cuda/final-candidate'}
    hashes={k:sha256(v) for k,v in binaries.items()}
    canonical=json.load(open('bench/hg-benchmark.json'))['canonical_outputs'];data=json.load(open('bench/hg-input.json'))
    for c in canonical:assert sha256(c['path'])==c['sha256']
    records=read_fasta(data['blocks'])
    report={'status':'running','runner_sha256':sha256(__file__),'binaries':{k:dict(path=v,sha256=hashes[k]) for k,v in binaries.items()},'input_manifest_sha256':sha256('bench/hg-input.json'),'protocol':'Screen CUDA workers 2,4,8,16 once; select fastest exact complete batch. One warmup each, three alternating measured pairs vs CPU16. Promote only >=5% median improvement, >=2/3 faster pairs and all correctness gates. No optional additional timing repetitions.','runs':[],'limitations':['Shared desktop GPU and CPU; no exclusive host or universal speed claim.','CUDA VRAM samples include shared primary context/module overhead; external display processes excluded by PID. Polling interval 0.5s may miss peaks.','CPU fallback disabled; failures abort acceptance.','Human chr22, not whole genome. Every original observation and seed retained.']}
    def run(label,mode,workers,reverse=False):
        assert all(sha256(binaries[k])==h for k,h in hashes.items())
        out=raw/label
        cmd=[binaries[mode],'bootstrap','--backend',mode,'--workers',str(workers),'--memory-mib','16384','--replicates','30','--seed',str(data['seed']),'--output-dir',str(out),'-p','4+25*2+4+6','-N','30','-t','15','-r','5','-I','0']
        if mode=='cuda':cmd+=['--cuda-memory-mib','1024','--cuda-tile-sites','16384']
        if reverse:cmd+=['--task-order','reverse']
        cmd+=[data['blocks']]
        stop=threading.Event();samples=[]
        def poll():
            while not stop.is_set():
                p=subprocess.run(['nvidia-smi','--query-compute-apps=pid,used_gpu_memory','--format=csv,noheader,nounits'],capture_output=True,text=True)
                # Dedicated benchmark executable paths distinguish other processes.
                for line in p.stdout.splitlines():
                    try:
                        pid,mib=map(int,line.split(','));exe=os.readlink(f'/proc/{pid}/exe')
                        if exe==str(ROOT/binaries[mode]):samples.append(mib)
                    except (ValueError,OSError):pass
                stop.wait(0.5)
        thread=threading.Thread(target=poll);thread.start()
        try:r=timed_run(cmd,ROOT/(str(out)+'-time'),env=env,timeout=2400)
        finally:stop.set();thread.join()
        r.update(label=label,backend=mode,requested_workers=workers,gpu_process_peak_mib=max(samples,default=0),gpu_samples=len(samples))
        assert r['exit_code']==0,r
        manifest=json.loads((out/'manifest.json').read_text());assert manifest['failed_replicates']==0 and manifest['nonfinite_replicates']==0
        comparisons=[]
        for i,c in enumerate(canonical):
            comparisons.append(compare_output(Path(c['path']).read_bytes(),(out/f'replicate-{i:02}.psmc').read_bytes()))
            selected,draws=draw_bootstrap(records,data['seed']+i)
            assert manifest['replicates'][i]['source_indices']==selected
            actual=[json.loads(line) for line in (out/f'replicate-{i:02}.draws.jsonl').read_text().splitlines()]
            assert actual[:-1]==[dict(event='bootstrap_draw',draw=j,**d) for j,d in enumerate(draws)]
            assert actual[-1]['accepted_sequences']==len(selected)
            stats=json.loads((out/f'replicate-{i:02}.stats.json').read_text())
            if mode=='cuda':assert stats['cuda_launches']>0 and stats['cuda_fallbacks']==0
        r.update(manifest=manifest,comparisons=comparisons,cpu_seconds=r['user_seconds']+r['system_seconds'])
        report['runs'].append(r);save('bench/cuda-benchmark.json',report)
        print(label,round(r['wall_seconds'],3),'CPU',round(r['cpu_seconds'],3),'GPU MiB',r['gpu_process_peak_mib'],flush=True)
        return r
    screen=[run(f'screen-cuda-{w}','cuda',w) for w in [2,4,8,16]]
    best=min(screen,key=lambda r:r['wall_seconds'])['requested_workers'];report['selected_cuda_workers']=best;save('bench/cuda-benchmark.json',report)
    run('warmup-cpu','cpu',16);run('warmup-cuda','cuda',best)
    for pair in range(3):
        for mode in (['cpu','cuda'] if pair%2==0 else ['cuda','cpu']):run(f'pair-{pair}-{mode}',mode,16 if mode=='cpu' else best)
    measured={m:[r for r in report['runs'] if r['label'].startswith('pair-') and r['backend']==m] for m in ['cpu','cuda']}
    summary={m:{key:statistics.median(r[key] for r in measured[m]) for key in ['wall_seconds','cpu_seconds','peak_rss_kib','gpu_process_peak_mib']} for m in measured}
    for m in measured:summary[m]['wall_range_seconds']=[min(r['wall_seconds'] for r in measured[m]),max(r['wall_seconds'] for r in measured[m])]
    wins=sum(measured['cuda'][i]['wall_seconds']<measured['cpu'][i]['wall_seconds'] for i in range(3))
    gain=1-summary['cuda']['wall_seconds']/summary['cpu']['wall_seconds'];report.update(status='passed',summary=summary,faster_pairs=wins,wall_reduction_fraction=gain,performance_promotion_gate=bool(gain>=0.05 and wins>=2))
    save('bench/cuda-benchmark.json',report);print(json.dumps(summary),flush=True)
if __name__=='__main__':main()
