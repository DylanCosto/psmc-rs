"""Independent ordered count chains per CUDA thread; same cell recurrences."""
import io,json,os,subprocess,tarfile
from pathlib import Path
from common import ROOT,save,sha256,timed_run,read_fasta,draw_bootstrap
from phase2_common import clean_env
from phase1_differential import compare_output
RAW=Path('work/exhaust/gpu-lanes')
def kernel(lanes):
    s=['// Independent per-cell binary64 chains; no parallel site reduction.', 'extern "C" __global__ void counts(const double* f,const double* b,const unsigned char* obs,const double* ae,double* a,int n,int sites,int reset) {',f' int base=(blockIdx.x*blockDim.x+threadIdx.x)*{lanes};',' if(base>=n*n)return;']
    for j in range(lanes):s += [f' int c{j}=base+{j},k{j}=c{j}/n,l{j}=c{j}%n; bool live{j}=c{j}<n*n;',f' double a{j}0=live{j}?ae[c{j}]:0.0,a{j}1=live{j}?ae[n*n+c{j}]:0.0,a{j}2=live{j}?ae[2*n*n+c{j}]:0.0;',f' double sum{j}=live{j}?(reset?1e-25:a[c{j}]):0.0;']
    s += [f' bool share=(n%{lanes})==0;', ' for(int u=0;u<sites;++u) {','  unsigned char z=obs[u];', '  double first_f=f[(long long)u*n+k0];']
    for j in range(lanes):s += [f'  if(live{j}) {{ double coefficient=z==0?a{j}0:(z==1?a{j}1:a{j}2);',f'   double value=share?first_f:f[(long long)u*n+k{j}]; double product=__dmul_rn(value,coefficient);',f'   sum{j}=__dadd_rn(sum{j},__dmul_rn(product,b[(long long)u*n+l{j}])); }}']
    s+=[' }']
    for j in range(lanes):s.append(f' if(live{j})a[c{j}]=sum{j};')
    return '\n'.join(s+['}'])+'\n'
def main():
    os.chdir(ROOT);RAW.mkdir()
    env={**clean_env(),'PSMC_NVRTC_LIBRARY':json.load(open('bench/cuda-environment.json'))['nvrtc_path']}
    r=dict(status='building',base='709831a',runner_sha256=sha256(__file__),variants={'cpu':dict(binary='bin/psmc-rs-v0.3.3'),'baseline':dict(binary='bin/psmc-rs-cuda')},runs=[])
    for lanes in [2,4]:
        label=f'lanes{lanes}';scratch=RAW/label;scratch.mkdir()
        archive=subprocess.check_output(['git','archive','709831a','Cargo.toml','Cargo.lock','rust-toolchain.toml','crates'])
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(scratch,filter='data')
        (scratch/'crates/psmc-cuda/src/counts.cu').write_text(kernel(lanes))
        p=scratch/'crates/psmc-cuda/src/driver.rs';s=p.read_text().replace('cells.div_ceil(128) as u32',f'cells.div_ceil({128*lanes}) as u32');p.write_text(s)
        commands=[['cargo','fmt','--all'],['cargo','test','--release','--locked','--offline','-p','psmc-cuda','--','--include-ignored','--test-threads=1'],['cargo','build','--release','--locked','--offline','-p','psmc-cli','--features','cuda']]
        for i,cmd in enumerate(commands):
            with (scratch/f'build-{i}.log').open('w') as log:subprocess.run(cmd,cwd=scratch,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        binary=scratch/'target/release/psmc-rs';r['variants'][label]=dict(binary=str(binary),sha256=sha256(binary),commands=commands,kernel_sha256=sha256(scratch/'crates/psmc-cuda/src/counts.cu'),driver_sha256=sha256(p));save('bench/exhaust-gpu-lanes.json',r);print('GPU lanes built',lanes,flush=True)
    data=json.load(open('bench/hg-input.json'));canonical=json.load(open('bench/hg-benchmark.json'))['canonical_outputs'];records=read_fasta(data['blocks'])
    for label,entry in r['variants'].items():
        backend='cpu' if label=='cpu' else 'cuda';out=RAW/('batch-'+label)
        cmd=[entry['binary'],'bootstrap','--backend',backend,'--workers','16','--memory-mib','16384','--replicates','30','--seed',str(data['seed']),'--output-dir',str(out),'-p','4+25*2+4+6','-N','30','-t','15','-r','5','-I','0',data['blocks']]
        run=timed_run(cmd,ROOT/RAW/(label+'-time'),env=env,timeout=1800);assert run['exit_code']==0
        manifest=json.loads((out/'manifest.json').read_text());assert manifest['failed_replicates']==0 and manifest['nonfinite_replicates']==0
        for i,c in enumerate(canonical):
            assert sha256(c['path'])==c['sha256'];compare_output(Path(c['path']).read_bytes(),(out/f'replicate-{i:02}.psmc').read_bytes())
            selected,_=draw_bootstrap(records,data['seed']+i);assert manifest['replicates'][i]['source_indices']==selected
        run.update(label=label,binary_sha256=sha256(entry['binary']),cpu_seconds=run['user_seconds']+run['system_seconds'],exact_outputs=30);r['runs'].append(run);save('bench/exhaust-gpu-lanes.json',r);print('GPU lanes batch',label,run['wall_seconds'],flush=True)
    r['status']='screened';save('bench/exhaust-gpu-lanes.json',r)
if __name__=='__main__':main()
