"""Overlap ordered scaling accumulation with independent forward state groups."""
import io,json,os,statistics,subprocess,tarfile
from pathlib import Path
from common import ROOT,save,sha256,timed_run
from phase2_common import clean_env
from phase1_differential import compare_output
RAW=Path('work/relook/forward')
REPORT='bench/relook-forward.json'
EXTRA_METADATA={}

def generate(scratch):
    p=scratch/'crates/psmc-cpu/src/simd.rs';s=p.read_text()
    start=s.index('    #[target_feature(enable = "avx")]\n    pub(super) unsafe fn forward64(')
    end=s.index('    #[target_feature(enable = "avx")]',start+10)
    old=s[start:end]
    new=old.replace('fn forward64(','fn forward_normalize64(',1).replace('    ) {','    ) -> f64 {',1)
    new=new.replace('        unsafe {','        let mut scale=0.0;\n        unsafe {',1)
    tail='''            }
        }
    }
'''
    assert new.endswith(tail)
    new=new[:-len(tail)]+'''                // Same ascending state additions, available after each group.
                for &value in &out[k..k+32] { scale+=value; }
            }
            normalize(out,scale);
        }
        scale
    }

'''
    s=s[:end]+new+s[end:]
    at=s.index('    pub(crate) fn normalize(')
    wrapper='''    pub(crate) fn forward_normalize64(self, out:&mut [f64], previous:&[f64], matrix:&[f64], emission:&[f64])->f64 {
        assert_eq!(out.len(),64); assert_eq!(previous.len(),64);
        assert_eq!(matrix.len(),4096); assert_eq!(emission.len(),64);
        #[cfg(target_arch="x86_64")]
        // SAFETY: runtime AVX capability and exact K64 dimensions; disjoint borrows.
        unsafe { return x86::forward_normalize64(out,previous,matrix,emission); }
        #[cfg(not(target_arch="x86_64"))]
        unreachable!("AVX capability unavailable");
    }

'''
    s=s[:at]+wrapper+s[at:]
    s+='''
#[cfg(test)]
mod relook_forward_tests {
 use super::*;
 #[test]
 fn fused_scale_retains_order_and_ieee_classes() {
  let Some(avx)=Avx::select(SimdMode::Auto,64).unwrap() else{return;};
  let vals=[0.0,-0.0,f64::from_bits(1),1e-300,0.1,1.0,1e300,f64::INFINITY,f64::NEG_INFINITY,f64::NAN];
  for mode in 0..3 {
   for offset in 0..vals.len() {
    let make=|n:usize,salt:usize|->Vec<f64>{(0..n).map(|i|if mode==0 {((i+salt)%101) as f64/103.0}else{vals[(i*7+salt+offset)%if mode==1 {7}else{vals.len()}]}).collect()};
    let f=make(65,2);let a=make(4097,5);let e=make(65,7);
    let mut expected=vec![0.0;64];avx.forward(&mut expected,&f[1..],&a[1..],&e[1..]);
    let mut scale=0.0;for &v in &expected {scale+=v;} for v in &mut expected {*v/=scale;}
    let mut actual=vec![123.0;66];let got=avx.forward_normalize64(&mut actual[1..65],&f[1..],&a[1..],&e[1..]);
    assert!(got.to_bits()==scale.to_bits() || got.is_nan()&&scale.is_nan());
    for (&x,&y) in actual[1..65].iter().zip(&expected) {assert!(x.to_bits()==y.to_bits() || x.is_nan()&&y.is_nan());}
    assert_eq!(actual[0],123.0);assert_eq!(actual[65],123.0);
   }
  }
 }
}
'''
    p.write_text(s)
    p=scratch/'crates/psmc-cpu/src/lib.rs';s=p.read_text()
    begin=s.index('            if let Some(avx) = self.avx {',s.index('        for u in 2..=length'))
    end=s.index('            messages.scales[u] = sum;',begin)
    original=s[begin:end]
    s=s[:begin]+'''            if let Some(avx)=self.avx.filter(|_|n==64) {
                sum=avx.forward_normalize64(current,previous,&model.transition,emission);
            } else {
'''+original+'            }\n'+s[end:];p.write_text(s)

def main():
    os.chdir(ROOT);RAW.mkdir(parents=True);scratch=RAW/'source';scratch.mkdir()
    archive=subprocess.check_output(['git','archive','30efe0b','Cargo.toml','Cargo.lock','rust-toolchain.toml','crates'])
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(scratch,filter='data')
    generate(scratch)
    commands=[['cargo','fmt','--all'],['cargo','test','--workspace','--release','--locked','--offline'],['cargo','build','--release','--locked','--offline','--bins','--examples']]
    for i,cmd in enumerate(commands):
        with (RAW/f'build-{i}.log').open('w') as log:subprocess.run(cmd,cwd=scratch,env=clean_env(),stdout=log,stderr=subprocess.STDOUT,check=True)
    variants={'installed':'bin/psmc-rs-v0.4.1','fused':str(scratch/'target/release/psmc-rs')}
    r=dict(status='running',base='30efe0b',runner_sha256=sha256(__file__),commands=commands,extra_metadata=EXTRA_METADATA,
           binaries={k:dict(path=v,sha256=sha256(v)) for k,v in variants.items()},source={str(p.relative_to(scratch)):sha256(p) for p in (scratch/'crates').rglob('*.rs')},runs=[])
    cases=[c for c in json.load(open('bench/cuda-profile.json'))['cases'] if c['id'] in ['hg-bootstrap01','k23-n30']]
    r['cases']=[{k:v for k,v in c.items() if k not in ['runs','cpu_seconds_medians']} for c in cases]
    for c in cases:
        for rep in range(4):
            for label in (['installed','fused'] if rep%2==0 else ['fused','installed']):
                binary=variants[label];cmd=['taskset','-c','0',binary,'--backend','cpu','--seed','42',*c['args'],c['input']]
                run=timed_run(cmd,ROOT/RAW/f'{c["id"]}-{rep}-{label}',env=clean_env(),timeout=600);assert run['exit_code']==0
                run.update(label=label,repeat=rep,case=c['id'],comparison=compare_output(Path(c['oracle']).read_bytes(),Path(run['output']).read_bytes()),cpu_seconds=run['user_seconds']+run['system_seconds'])
                r['runs'].append(run);save(REPORT,r);print(str(RAW),c['id'],rep,label,run['wall_seconds'],flush=True)
    r['summary']={c['id']:{label:{key:statistics.median(x[key] for x in r['runs'] if x['case']==c['id'] and x['label']==label and x['repeat']>0) for key in ['wall_seconds','cpu_seconds','peak_rss_kib']} for label in variants} for c in cases}
    r['status']='screened';save(REPORT,r);print(r['summary'],flush=True)
if __name__=='__main__':main()
