"""Disposable pinned/stream-local transfer and launch-geometry experiments."""
import io,json,os,subprocess,tarfile,argparse,statistics
from pathlib import Path
from common import ROOT,save,sha256,timed_run
from phase2_common import clean_env
from phase1_differential import compare_output
BASE='709831a';RAW=Path('work/exhaust/cuda');REPORT='bench/exhaust-cuda.json'
def replace(s,a,b):
    assert s.count(a)==1,a[:80]
    return s.replace(a,b)
def patch(path,pipeline,threads):
    s=path.read_text()
    s=replace(s,'    htod: unsafe extern', '''    host_alloc: unsafe extern "C" fn(*mut Handle,usize,c_uint)->c_int = c"cuMemHostAlloc",
    host_free: unsafe extern "C" fn(Handle)->c_int = c"cuMemFreeHost",
    htod_async: unsafe extern "C" fn(DevicePtr,*const c_void,usize,Handle)->c_int = c"cuMemcpyHtoDAsync_v2",
    htod: unsafe extern''')
    s=replace(s,'pub struct Device {','''#[derive(Default)]
struct Pinned { ptr: Handle, capacity: usize }
pub struct Device {''')
    s=replace(s,'    buffers: [Buffer; 5], // f, next b, symbols, ae, counts','''    buffers: [Buffer; 5], // f, next b, symbols, ae, counts
    pinned: [Pinned; 7], // two host banks for f/b/obs, one for ae
    slot: usize,''')
    s=replace(s,'            buffers: std::array::from_fn(|_| Buffer::default()),','''            buffers: std::array::from_fn(|_| Buffer::default()),
            pinned: std::array::from_fn(|_| Pinned::default()),
            slot: 0,''')
    s=replace(s,'        if bytes > b.capacity {','''        if bytes > b.capacity {
            unsafe { check((self.api.sync)(self.stream), "drain before buffer growth")?; }''')
    start=s.index('    fn upload_f64(');end=s.index('    /// Caller validates',start)
    s=s[:start]+'''    fn upload(&mut self, index: usize, source: *const c_void, bytes: usize) -> Result<()> {
        self.ensure(index, bytes)?;
        let host = if index == 3 { 6 } else { 2*index + self.slot };
        let p = &mut self.pinned[host];
        // All host buffers belong to this thread. Drain queued reads before
        // reallocating; callers drain the two-bank ring before overwriting it.
        unsafe {
            if bytes > p.capacity {
                check((self.api.sync)(self.stream), "drain before pinned growth")?;
                if !p.ptr.is_null() { check((self.api.host_free)(p.ptr), "cuMemFreeHost")?; p.ptr=ptr::null_mut(); p.capacity=0; }
                check((self.api.host_alloc)(&mut p.ptr,bytes,0), "cuMemHostAlloc")?;
                p.capacity=bytes;
            }
            ptr::copy_nonoverlapping(source.cast::<u8>(), p.ptr.cast::<u8>(), bytes);
            check((self.api.htod_async)(self.buffers[index].ptr,p.ptr,bytes,self.stream), "cuMemcpyHtoDAsync")
        }
    }
    fn upload_f64(&mut self, index: usize, values: &[f64]) -> Result<()> {
        self.upload(index, values.as_ptr().cast(), std::mem::size_of_val(values))
    }
    pub fn prepare(&mut self, ae: &[f64]) -> Result<()> {
        self.activate()?;
        unsafe { check((self.api.sync)(self.stream), "drain before new model")?; }
        self.slot=0;
        self.upload_f64(3,ae)
    }
'''+s[end:]
    s=replace(s,'        self.upload_f64(0, f)?;','''        self.activate()?;
        if self.slot == 0 {
            unsafe { check((self.api.sync)(self.stream), "drain before host ring reuse")?; }
        }
        self.upload_f64(0, f)?;''')
    start=s.index('        unsafe {\n            check(\n                (self.api.htod)(self.buffers[2]');end=s.index('        let mut pointers:',start)
    s=s[:start]+'''        self.upload(2, obs.as_ptr().cast(), obs.len())?;
'''+s[end:]
    start=s.index('            // Pageable synchronous');end=s.index('            check(\n                (self.api.launch)',start)
    s=s[:start]+'''            // Copies and kernels share the worker stream; no global dependency.
'''+s[end:]
    s=replace(s,'cells.div_ceil(128) as u32',f'cells.div_ceil({threads}) as u32')
    s=replace(s,'                    128,',f'                    {threads},')
    old='            check((self.api.sync)(self.stream), "cuStreamSynchronize")?;'
    new=old if not pipeline else '            if last { check((self.api.sync)(self.stream), "cuStreamSynchronize")?; }'
    s=replace(s,old,new)
    s=replace(s,'        Ok(())\n    }\n}\nimpl Drop for Device',f'        self.slot = (self.slot + 1) % {2 if pipeline else 1};\n        Ok(())\n    }}\n}}\nimpl Drop for Device')
    s=replace(s,'            for b in &self.buffers {','''            for p in &self.pinned {
                if !p.ptr.is_null() { (self.api.host_free)(p.ptr); }
            }
            for b in &self.buffers {''')
    path.write_text(s)
def env():return {**clean_env(),'PSMC_NVRTC_LIBRARY':json.loads(Path('bench/cuda-environment.json').read_text())['nvrtc_path']}
def build():
    RAW.mkdir(parents=True)
    r=dict(status='building',base=BASE,runner_sha256=sha256(__file__),variants={'baseline':dict(binary='bin/psmc-rs-cuda',sha256=sha256('bin/psmc-rs-cuda'))},runs=[])
    for label,pipeline,threads in [('pinned',False,128),('pipeline',True,128),('pipeline32',True,32),('pipeline64',True,64)]:
        scratch=RAW/label;scratch.mkdir()
        archive=subprocess.check_output(['git','archive',BASE,'Cargo.toml','Cargo.lock','rust-toolchain.toml','crates'])
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(scratch,filter='data')
        patch(scratch/'crates/psmc-cuda/src/driver.rs',pipeline,threads)
        commands=[['cargo','fmt','--all'],['cargo','test','--release','--locked','--offline','-p','psmc-cuda','--','--include-ignored','--test-threads=1'],['cargo','build','--release','--locked','--offline','-p','psmc-cli','--features','cuda']]
        for i,cmd in enumerate(commands):
            with (scratch/f'build-{i}.log').open('w') as log:subprocess.run(cmd,cwd=scratch,env=env(),stdout=log,stderr=subprocess.STDOUT,check=True)
        binary=scratch/'target/release/psmc-rs'
        r['variants'][label]=dict(binary=str(binary),sha256=sha256(binary),pipeline=pipeline,threads=threads,commands=commands,source_sha256=sha256(scratch/'crates/psmc-cuda/src/driver.rs'))
        save(REPORT,r);print('GPU built/tested '+label,flush=True)
    r['status']='built';save(REPORT,r)
def screen():
    r=json.loads(Path(REPORT).read_text());assert r['status']=='built'
    c=next(c for c in json.loads(Path('bench/cuda-profile.json').read_text())['cases'] if c['id']=='hg-bootstrap01')
    r['case']=c
    for rep in range(4):
        labels=list(r['variants']);labels=labels[rep:]+labels[:rep]
        for label in labels:
            v=r['variants'][label];assert sha256(v['binary'])==v['sha256']
            cmd=['taskset','-c','0',v['binary'],'--backend','cuda','--seed','42',*c['args'],c['input']]
            run=timed_run(cmd,ROOT/RAW/f'screen-{rep}-{label}',env=env(),timeout=600);assert run['exit_code']==0
            compare_output(Path(c['oracle']).read_bytes(),Path(run['output']).read_bytes())
            run.update(label=label,repeat=rep,exact=True,cpu_seconds=run['user_seconds']+run['system_seconds']);r['runs'].append(run);save(REPORT,r)
            print('GPU',rep,label,round(run['wall_seconds'],3),flush=True)
    r['summary']={label:{key:statistics.median(x[key] for x in r['runs'] if x['label']==label and x['repeat']>0) for key in ['wall_seconds','cpu_seconds','peak_rss_kib']} for label in r['variants']}
    r['status']='screened';save(REPORT,r);print(json.dumps(r['summary']),flush=True)
if __name__=='__main__':
    os.chdir(ROOT);p=argparse.ArgumentParser();p.add_argument('action',choices=['build','screen']);globals()[p.parse_args().action]()
