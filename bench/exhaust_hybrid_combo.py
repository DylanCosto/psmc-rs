"""Explicit CPU/CUDA job split experiment; no approximate or automatic fallback."""
import io,json,os,subprocess,tarfile,argparse
from pathlib import Path
from common import ROOT,save,sha256,timed_run,read_fasta,draw_bootstrap
from phase2_common import clean_env
from phase1_differential import compare_output
RAW=Path('work/exhaust/hybrid-combo')
def main():
    os.chdir(ROOT);RAW.mkdir();scratch=RAW/'source';scratch.mkdir()
    archive=subprocess.check_output(['git','archive','709831a','Cargo.toml','Cargo.lock','rust-toolchain.toml','crates'])
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(scratch,filter='data')
    # One predeclared combination: CPU candidate + record lookahead + blocking waits.
    for name in ['lib.rs','simd.rs']:
        (scratch/'crates/psmc-cpu/src'/name).write_bytes((ROOT/'crates/psmc-cpu/src'/name).read_bytes())
    for name in ['lib.rs','driver.rs']:
        (scratch/'crates/psmc-cuda/src'/name).write_bytes((ROOT/'work/exhaust/lookahead/source/crates/psmc-cuda/src'/name).read_bytes())
    driver=scratch/'crates/psmc-cuda/src/driver.rs';ds=driver.read_text()
    ds=ds.replace('    retain: unsafe extern','    primary_flags: unsafe extern "C" fn(c_int,c_uint)->c_int = c"cuDevicePrimaryCtxSetFlags_v2",\n    retain: unsafe extern')
    token='            check((api.device)(&mut device, 0), "cuDeviceGet")?;'
    assert ds.count(token)==1;ds=ds.replace(token,token+'\n            check((api.primary_flags)(device,4), "cuDevicePrimaryCtxSetFlags")?;');driver.write_text(ds)
    p=scratch/'crates/psmc-cli/src/batch.rs';s=p.read_text();old='''                        job(&options, &sequences, &directory, index, seed + index as i64)'''
    new='''                        let mut selected = options.clone();
                        let gpu_jobs: usize = std::env::var("PSMC_EXPERIMENT_GPU_JOBS").expect("experiment GPU job count").parse().expect("integer job count");
                        if index >= gpu_jobs { selected.backend = "cpu".into(); }
                        job(&selected, &sequences, &directory, index, seed + index as i64)'''
    assert s.count(old)==1;s=s.replace(old,new);p.write_text(s)
    env={**clean_env(),'PSMC_NVRTC_LIBRARY':json.load(open('bench/cuda-environment.json'))['nvrtc_path']}
    with (RAW/'tests.log').open('w') as f:
        subprocess.run(['cargo','test','--workspace','--release','--locked','--offline','--','--include-ignored','--test-threads=1'],cwd=scratch,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
    cmd=['cargo','build','--release','--locked','--offline','-p','psmc-cli','--features','cuda']
    with (RAW/'build.log').open('w') as f:subprocess.run(cmd,cwd=scratch,env=clean_env(),stdout=f,stderr=subprocess.STDOUT,check=True)
    binary=str(scratch/'target/release/psmc-rs');data=json.load(open('bench/hg-input.json'));canonical=json.load(open('bench/hg-benchmark.json'))['canonical_outputs'];records=read_fasta(data['blocks'])
    r=dict(status='running',binary=binary,binary_sha256=sha256(binary),source_sha256=sha256(p),source_files={str(f.relative_to(scratch)):sha256(f) for f in (scratch/'crates').rglob('*') if f.suffix in ['.rs','.cu']},runner_sha256=sha256(__file__),build_command=cmd,runs=[],protocol='Fixed first 0/8/15/30 of 30 complete fits use blocking CUDA with record lookahead and 65536-site tiles; all configurations include provisional CPU optimizations; remaining fits explicitly select CPU. One batch each, dynamic queue, 16 workers. Per-replicate stats record actual backend. No fallback.')
    for gpu_jobs in [0,8,15,30]:
        out=RAW/f'gpu{gpu_jobs}'
        cmd=[binary,'bootstrap','--backend','cuda','--workers','16','--memory-mib','16384','--replicates','30','--seed',str(data['seed']),'--output-dir',str(out),'-p','4+25*2+4+6','-N','30','-t','15','-r','5','-I','0',data['blocks']]
        cmd+=['--cuda-tile-sites','65536','--cuda-memory-mib','2048']
        env={**clean_env(),'PSMC_EXPERIMENT_GPU_JOBS':str(gpu_jobs),'PSMC_NVRTC_LIBRARY':json.load(open('bench/cuda-environment.json'))['nvrtc_path']}
        run=timed_run(cmd,ROOT/RAW/f'gpu{gpu_jobs}-time',env=env,timeout=1800);assert run['exit_code']==0
        manifest=json.loads((out/'manifest.json').read_text());assert manifest['failed_replicates']==0 and manifest['nonfinite_replicates']==0
        for i,c in enumerate(canonical):
            assert sha256(c['path'])==c['sha256'];compare_output(Path(c['path']).read_bytes(),(out/f'replicate-{i:02}.psmc').read_bytes())
            selected,_=draw_bootstrap(records,data['seed']+i);assert manifest['replicates'][i]['source_indices']==selected
            stats=json.loads((out/f'replicate-{i:02}.stats.json').read_text());assert stats['backend']==('cuda' if i<gpu_jobs else 'cpu')
        run.update(gpu_jobs=gpu_jobs,cpu_seconds=run['user_seconds']+run['system_seconds'],exact_outputs=30);r['runs'].append(run);save('bench/exhaust-hybrid-combo.json',r);print('hybrid',gpu_jobs,run['wall_seconds'],flush=True)
    r['status']='screened';save('bench/exhaust-hybrid-combo.json',r)
if __name__=='__main__':main()
