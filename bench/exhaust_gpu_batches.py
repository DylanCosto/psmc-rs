"""One complete 30-replicate screening batch per CUDA transfer/geometry variant."""
import os,json,threading,subprocess,time
from pathlib import Path
from common import ROOT,save,sha256,timed_run,read_fasta,draw_bootstrap
from phase2_common import clean_env
from phase1_differential import compare_output

def main():
    os.chdir(ROOT);raw=Path('work/exhaust/gpu-batches');raw.mkdir()
    prior=json.load(open('bench/exhaust-cuda.json'));data=json.load(open('bench/hg-input.json'));canonical=json.load(open('bench/hg-benchmark.json'))['canonical_outputs'];records=read_fasta(data['blocks'])
    variants={'cpu':dict(binary='bin/psmc-rs-v0.3.3'),**prior['variants']}
    variants['baseline-large']=dict(binary=prior['variants']['baseline']['binary'],tile=65536)
    lookahead=json.load(open('bench/exhaust-lookahead.json'))
    variants['lookahead']=dict(binary=lookahead['binary'])
    variants['lookahead-large']=dict(binary=lookahead['binary'],tile=65536)
    variants.update(json.load(open('bench/exhaust-wait-policy.json'))['variants'])
    r=dict(status='running',runner_sha256=sha256(__file__),input_sha256=sha256(data['blocks']),variants=variants,runs=[],protocol='One full screening batch per variant, 16 workers. No speed claim; fresh fixed pairs required for promotion.')
    for label,entry in variants.items():
        out=raw/label;backend='cpu' if label=='cpu' else 'cuda'
        cmd=[entry['binary'],'bootstrap','--backend',backend,'--workers','16','--memory-mib','16384','--replicates','30','--seed',str(data['seed']),'--output-dir',str(out),'-p','4+25*2+4+6','-N','30','-t','15','-r','5','-I','0',data['blocks']]
        if backend=='cuda':cmd+=['--cuda-tile-sites',str(entry.get('tile',16384)),'--cuda-memory-mib','2048']
        stop=threading.Event();samples=[]
        def poll():
            while not stop.is_set():
                q=subprocess.run(['nvidia-smi','--query-gpu=utilization.gpu,utilization.memory,power.draw,memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True)
                try:samples.append(dict(time=time.time(),values=[float(x.strip()) for x in q.stdout.strip().split(',')]))
                except ValueError:pass
                stop.wait(1)
        monitor=threading.Thread(target=poll);monitor.start()
        try:run=timed_run(cmd,ROOT/raw/(label+'-time'),env={**clean_env(),'PSMC_NVRTC_LIBRARY':json.load(open('bench/cuda-environment.json'))['nvrtc_path']},timeout=1800)
        finally:stop.set();monitor.join()
        run['device_samples']=samples
        run['device_sample_scope']='Entire shared GPU including desktop; coarse 1-second polling, diagnostic only.'
        assert run['exit_code']==0
        manifest=json.loads((out/'manifest.json').read_text());assert manifest['failed_replicates']==0 and manifest['nonfinite_replicates']==0
        for i,c in enumerate(canonical):
            assert sha256(c['path'])==c['sha256'];compare_output(Path(c['path']).read_bytes(),(out/f'replicate-{i:02}.psmc').read_bytes())
            selected,_=draw_bootstrap(records,data['seed']+i);assert manifest['replicates'][i]['source_indices']==selected
        run.update(label=label,binary_sha256=sha256(entry['binary']),cpu_seconds=run['user_seconds']+run['system_seconds'],exact_outputs=30);r['runs'].append(run);save('bench/exhaust-gpu-batches.json',r);print('GPU batch',label,run['wall_seconds'],flush=True)
    r['status']='screened';save('bench/exhaust-gpu-batches.json',r)
if __name__=='__main__':main()
