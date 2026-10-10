"""Native codegen and bounded exact model/objective memoization candidates."""
import io,json,os,subprocess,tarfile,argparse,statistics
from pathlib import Path
from common import ROOT,save,sha256,timed_run
from phase2_common import clean_env
from phase1_differential import compare_output
BASE='709831a';RAW=Path('work/exhaust/more');REPORT='bench/exhaust-more.json'
def memo(scratch):
    # Cache both the full model and Q: optimizer callback/model side effects and
    # observer event order are preserved even on a hit. Cleared every E-step.
    p=scratch/'crates/psmc-cpu/src/engine.rs';s=p.read_text()
    pairs=[('    counters: BackendStats,','''    counters: BackendStats,
    memo: std::cell::RefCell<HashMap<Vec<u64>, (Model, Option<f64>)>>,'''),('            counters: BackendStats::default(),','''            counters: BackendStats::default(),
            memo: std::cell::RefCell::new(HashMap::new()),'''),('        let prepared = self.workspace.prepare(model);','''        self.memo.borrow_mut().clear();
        let prepared = self.workspace.prepare(model);'''),('''        self.model_workspace.update(model, settings);
        self.counters.model_updates += 1;''','''        let key: Vec<_> = model.params.iter().map(|x| x.to_bits()).collect();
        let finite = model.params.iter().all(|x| x.is_finite());
        if finite {
            if let Some((saved, _)) = self.memo.borrow().get(&key) {
                model.clone_from(saved);
                self.counters.model_updates += 1;
                return;
            }
        }
        self.model_workspace.update(model, settings);
        self.counters.model_updates += 1;
        if finite {
            let mut memo = self.memo.borrow_mut();
            if memo.len() >= 128 { memo.clear(); }
            memo.insert(key, (model.clone(), None));
        }'''),('    fn stats(&self) -> BackendStats {','''    fn q(&self, counts: &Counts, model: &Model) -> f64 {
        let key: Vec<_> = model.params.iter().map(|x| x.to_bits()).collect();
        let mut memo = self.memo.borrow_mut();
        if let Some((_, value)) = memo.get_mut(&key) {
            if let Some(q) = *value { return q; }
            let q=counts.q(model); *value=Some(q); return q;
        }
        counts.q(model)
    }
    fn stats(&self) -> BackendStats {''')]
    for a,b in pairs:assert s.count(a)==1,a;s=s.replace(a,b)
    p.write_text(s)
def normalize(scratch, k64=False):
    p=scratch/'crates/psmc-cpu/src/simd.rs';s=p.read_text()
    at='    pub(crate) fn backward(self, out: &mut [f64], next: &[f64], transpose: &[f64], scale: f64) {'
    s=s.replace(at,'''    pub(crate) fn normalize(self, out: &mut [f64], scale: f64) {
        #[cfg(target_arch = "x86_64")]
        // SAFETY: detected AVX capability; complete four-lane chunks and scalar tail.
        unsafe { x86::normalize(out, scale); }
        #[cfg(not(target_arch = "x86_64"))]
        unreachable!("AVX capability unavailable");
    }

'''+at)
    at='    use std::arch::x86_64::*;'
    s=s.replace(at,at+'''
    #[target_feature(enable = "avx")]
    pub(super) unsafe fn normalize(out: &mut [f64], scale: f64) {
        unsafe {
            let v = _mm256_set1_pd(scale);
            let end = out.len()/4*4;
            for k in (0..end).step_by(4) {
                let p=out.as_mut_ptr().add(k);
                _mm256_storeu_pd(p,_mm256_div_pd(_mm256_loadu_pd(p),v));
            }
            for value in &mut out[end..] { *value /= scale; }
        }
    }
''');p.write_text(s)
    p=scratch/'crates/psmc-cpu/src/lib.rs';s=p.read_text()
    a='''            for target in current {
                *target /= sum;
            }'''
    assert s.count(a)==1
    s=s.replace(a,'''            if let Some(avx) = self.avx {
                avx.normalize(current,sum);
            } else {
                for target in current { *target /= sum; }
            }''')
    if k64: s=s.replace('if let Some(avx) = self.avx {\n                avx.normalize', 'if let Some(avx) = self.avx.filter(|_| n == 64) {\n                avx.normalize')
    p.write_text(s)
def build():
    RAW.mkdir(parents=True)
    r=dict(status='building',base=BASE,runner_sha256=sha256(__file__),variants={'baseline':dict(binary='work/exhaust/cpu/baseline/target/release/psmc-rs',sha256=sha256('work/exhaust/cpu/baseline/target/release/psmc-rs'))},runs=[])
    for label in ['native','memo','normalize']:
        scratch=RAW/label;scratch.mkdir()
        archive=subprocess.check_output(['git','archive',BASE,'Cargo.toml','Cargo.lock','rust-toolchain.toml','crates'])
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(scratch,filter='data')
        if label=='memo':memo(scratch)
        if label=='normalize':normalize(scratch)
        env={**clean_env(),'CARGO_BUILD_JOBS':'16'}
        if label=='native':env['RUSTFLAGS']='-C target-cpu=native'
        commands=[['cargo','fmt','--all'],['cargo','test','--release','--locked','--offline','--workspace'],['cargo','build','--release','--locked','--offline']]
        for i,cmd in enumerate(commands):
            with (scratch/f'build-{i}.log').open('w') as log:subprocess.run(cmd,cwd=scratch,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        binary=scratch/'target/release/psmc-rs';r['variants'][label]=dict(binary=str(binary),sha256=sha256(binary),commands=commands,rustflags=env.get('RUSTFLAGS',''),source={str(p.relative_to(scratch)):sha256(p) for p in (scratch/'crates').rglob('*.rs')})
        save(REPORT,r);print('built '+label,flush=True)
    r['status']='built';save(REPORT,r)
def screen():
    r=json.loads(Path(REPORT).read_text());assert r['status']=='built'
    cases=[c for c in json.loads(Path('bench/cuda-profile.json').read_text())['cases'] if c['id'] in ['hg-bootstrap01','k23-n30','bootstrap-00-k23-n30']]
    r['cases']=cases
    for c in cases:
        for rep in range(4):
            labels=list(r['variants']);labels=labels[rep%len(labels):]+labels[:rep%len(labels)]
            for label in labels:
                v=r['variants'][label];assert sha256(v['binary'])==v['sha256']
                cmd=['taskset','-c','0',v['binary'],'--backend','cpu','--seed','42',*c['args'],c['input']]
                run=timed_run(cmd,ROOT/RAW/f'{c["id"]}-{rep}-{label}',env=clean_env(),timeout=600);assert run['exit_code']==0
                compare_output(Path(c['oracle']).read_bytes(),Path(run['output']).read_bytes())
                run.update(label=label,case=c['id'],repeat=rep,exact=True,cpu_seconds=run['user_seconds']+run['system_seconds']);r['runs'].append(run);save(REPORT,r);print(c['id'],rep,label,run['wall_seconds'],flush=True)
    r['summary']={c['id']:{label:{key:statistics.median(x[key] for x in r['runs'] if x['case']==c['id'] and x['label']==label and x['repeat']>0) for key in ['wall_seconds','cpu_seconds','peak_rss_kib']} for label in r['variants']} for c in cases}
    r['status']='screened';save(REPORT,r);print(json.dumps(r['summary']),flush=True)
if __name__=='__main__':
    os.chdir(ROOT);p=argparse.ArgumentParser();p.add_argument('action',choices=['build','screen']);globals()[p.parse_args().action]()
