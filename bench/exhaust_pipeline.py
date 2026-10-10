"""CPU-next-record/GPU-count overlap prototype, snapshot path stays synchronous."""
import io,json,os,subprocess,tarfile,argparse
from pathlib import Path
from common import ROOT,save,sha256
from phase2_common import clean_env
RAW=Path('work/exhaust/lookahead')
def main():
    os.chdir(ROOT);RAW.mkdir();scratch=RAW/'source';scratch.mkdir()
    archive=subprocess.check_output(['git','archive','709831a','Cargo.toml','Cargo.lock','rust-toolchain.toml','crates'])
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(scratch,filter='data')
    p=scratch/'crates/psmc-cuda/src/driver.rs';s=p.read_text().replace('    _thread_bound: PhantomData<Rc<()>>,','    deferred: bool,\n    _thread_bound: PhantomData<Rc<()>>,').replace('            _thread_bound: PhantomData,','            deferred: false,\n            _thread_bound: PhantomData,')
    s=s.replace('            check((self.api.sync)(self.stream), "cuStreamSynchronize")?;','            if !last || !self.deferred {check((self.api.sync)(self.stream), "cuStreamSynchronize")?;}').replace('            if last {','            if last && !self.deferred {')
    at='    fn activate(&self) -> Result<()> {'
    s=s.replace(at,'''    pub fn set_deferred(&mut self, value: bool) { self.deferred=value; }
    pub fn finish(&mut self, out: &mut [f64]) -> Result<()> {
        self.activate()?;
        if std::mem::size_of_val(out)!=self.buffers[4].capacity {return Err("deferred output shape mismatch".into());}
        unsafe {
            check((self.api.sync)(self.stream),"finish deferred record")?;
            check((self.api.dtoh)(out.as_mut_ptr().cast(),self.buffers[4].ptr,std::mem::size_of_val(out)),"download deferred record")
        }
    }
'''+at);p.write_text(s)
    p=scratch/'crates/psmc-cuda/src/lib.rs';s=p.read_text();at='        let prepared = self.workspace.prepare(model);'
    assert s.count(at)==1;s=s.replace(at,'''        if !observer.needs_sequence_messages() && !self.profile {
            return self.pipelined(model,sequences);
        }
        self.device.set_deferred(false);
'''+at);s+='\n'+Path('bench/exhaust_pipeline.rs').read_text();p.write_text(s)
    env={**clean_env(),'PSMC_NVRTC_LIBRARY':json.load(open('bench/cuda-environment.json'))['nvrtc_path']}
    commands=[['cargo','fmt','--all'],['cargo','test','--release','--locked','--offline','-p','psmc-cuda','--','--include-ignored','--test-threads=1'],['cargo','build','--release','--locked','--offline','-p','psmc-cli','--features','cuda']]
    for i,cmd in enumerate(commands):
        with (RAW/f'build-{i}.log').open('w') as log:subprocess.run(cmd,cwd=scratch,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    binary=scratch/'target/release/psmc-rs'
    save('bench/exhaust-lookahead.json',dict(status='built',binary=str(binary),binary_sha256=sha256(binary),commands=commands,source={str(p.relative_to(scratch)):sha256(p) for p in (scratch/'crates').rglob('*.rs')},limitations=['Isolated experiment; profiling and snapshots use original synchronous path. All performance runs must leave profiling disabled.']))
if __name__=='__main__':main()
