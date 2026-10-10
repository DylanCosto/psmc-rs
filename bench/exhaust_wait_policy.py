"""CUDA yielding/blocking waits: avoid burning CPU cycles while GPU runs."""
import io,json,os,subprocess,tarfile
from pathlib import Path
from common import ROOT,save,sha256
from phase2_common import clean_env
RAW=Path('work/exhaust/wait-policy')
def main():
    os.chdir(ROOT);RAW.mkdir()
    r=dict(status='building',base='709831a',runner_sha256=sha256(__file__),variants={})
    for label,flags in [('yield',2),('blocking',4)]:
        scratch=RAW/label;scratch.mkdir()
        archive=subprocess.check_output(['git','archive','709831a','Cargo.toml','Cargo.lock','rust-toolchain.toml','crates'])
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(scratch,filter='data')
        p=scratch/'crates/psmc-cuda/src/driver.rs';s=p.read_text()
        s=s.replace('    retain: unsafe extern','    primary_flags: unsafe extern "C" fn(c_int,c_uint)->c_int = c"cuDevicePrimaryCtxSetFlags_v2",\n    retain: unsafe extern')
        at='            check((api.device)(&mut device, 0), "cuDeviceGet")?;'
        assert s.count(at)==1;s=s.replace(at,at+f'\n            check((api.primary_flags)(device,{flags}), "cuDevicePrimaryCtxSetFlags")?;');p.write_text(s)
        env={**clean_env(),'PSMC_NVRTC_LIBRARY':json.load(open('bench/cuda-environment.json'))['nvrtc_path']}
        commands=[['cargo','fmt','--all'],['cargo','test','--release','--locked','--offline','-p','psmc-cuda','--','--include-ignored','--test-threads=1'],['cargo','build','--release','--locked','--offline','-p','psmc-cli','--features','cuda']]
        for i,cmd in enumerate(commands):
            with (scratch/f'build-{i}.log').open('w') as f:subprocess.run(cmd,cwd=scratch,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
        binary=scratch/'target/release/psmc-rs';r['variants'][label]=dict(binary=str(binary),sha256=sha256(binary),flags=flags,source_sha256=sha256(p),commands=commands);save('bench/exhaust-wait-policy.json',r);print('built wait policy',label,flush=True)
    r['status']='built';save('bench/exhaust-wait-policy.json',r)
if __name__=='__main__':main()
