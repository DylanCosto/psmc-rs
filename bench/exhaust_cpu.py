"""Final bounded CPU count search; disposable source trees, exact-gated screens."""
import io,json,os,subprocess,tarfile,statistics,argparse
from pathlib import Path
from common import ROOT,save,sha256,timed_run
from phase2_common import clean_env
from phase1_differential import compare_output
from cpu_next_candidates import function_replace
BASE='709831a'; RAW=Path('work/exhaust/cpu'); REPORT='bench/exhaust-cpu.json'
CONFIGS={'sites16':(1,32,16),'sites32':(1,32,32),'sites64':(1,32,64),'joint2':(2,16,8),'joint4':(4,8,8),'joint2s16':(2,16,16)}
def generate(path,kb,width,sites):
    lines=['    #[target_feature(enable = "avx")]', '    pub(super) unsafe fn counts_sequence64(counts: &mut [f64], observations: &[u8], forward: &[f64], backward: &[f64], products: &[f64]) {',
      '        // Independent count cells; original ascending sites and multiply grouping.',
      '        // SAFETY: wrapper checks shapes; k+kb<=64 and l+width<=64.',
      '        unsafe {',f'            for begin in (1..observations.len()).step_by({sites}) {{',f'                let end = (begin + {sites}).min(observations.len());',f'                for k in (0..64).step_by({kb}) {{',f'                    for l in (0..64).step_by({width}) {{']
    for a in range(kb):
        for j in range(width//4):lines.append(f'                        let mut sum{a}_{j} = _mm256_loadu_pd(counts.as_ptr().add((k+{a})*64+l+{4*j}));')
    lines+=['                        for u in begin..end {','                            let row = *observations.get_unchecked(u) as usize*4096+k*64+l;','                            let next = (u+1)*64+l;']
    for a in range(kb):lines.append(f'                            let f{a} = _mm256_set1_pd(*forward.get_unchecked(u*64+k+{a}));')
    for j in range(width//4):
        lines.append(f'                            let b{j} = _mm256_loadu_pd(backward.as_ptr().add(next+{4*j}));')
        for a in range(kb):lines += [f'                            let first{a}_{j} = _mm256_mul_pd(f{a}, _mm256_loadu_pd(products.as_ptr().add(row+{64*a+4*j})));',f'                            sum{a}_{j} = _mm256_add_pd(sum{a}_{j}, _mm256_mul_pd(first{a}_{j}, b{j}));']
    lines+=['                        }']
    for a in range(kb):
        for j in range(width//4):lines.append(f'                        _mm256_storeu_pd(counts.as_mut_ptr().add((k+{a})*64+l+{4*j}),sum{a}_{j});')
    lines+=['                    }','                }','            }','        }','    }']
    function_replace(path,'counts_sequence64','\n'.join(lines))
def build():
    RAW.mkdir(parents=True)
    r=dict(status='building',base=BASE,runner_sha256=sha256(__file__),variants={},runs=[])
    for label,config in {'baseline':None,**CONFIGS}.items():
        scratch=RAW/label;scratch.mkdir()
        archive=subprocess.check_output(['git','archive',BASE,'Cargo.toml','Cargo.lock','rust-toolchain.toml','crates'])
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(scratch,filter='data')
        if config:generate(scratch/'crates/psmc-cpu/src/simd.rs',*config)
        commands=[['cargo','fmt','--all'],['cargo','test','--workspace','--release','--locked','--offline'],['cargo','build','--release','--locked','--offline','--bins','--examples']]
        for i,cmd in enumerate(commands):
            with (scratch/f'build-{i}.log').open('w') as log:subprocess.run(cmd,cwd=scratch,env={**clean_env(),'CARGO_BUILD_JOBS':'16'},stdout=log,stderr=subprocess.STDOUT,check=True)
        binary=scratch/'target/release/psmc-rs'
        r['variants'][label]=dict(binary=str(binary),sha256=sha256(binary),config=config,commands=commands,source={str(p.relative_to(scratch)):sha256(p) for p in (scratch/'crates').rglob('*.rs')})
        save(REPORT,r);print('built '+label,flush=True)
    r['status']='built';save(REPORT,r)
def screen():
    r=json.loads(Path(REPORT).read_text());assert r['status']=='built'
    cases=[c for c in json.loads(Path('bench/cuda-profile.json').read_text())['cases'] if c['id'] in ['hg-bootstrap01','k23-n30']]
    r['cases']=cases
    for c in cases:
        for rep in range(4):
            labels=list(r['variants']);labels=labels[rep:]+labels[:rep]
            for label in labels:
                v=r['variants'][label];assert sha256(v['binary'])==v['sha256']
                cmd=['taskset','-c','0',v['binary'],'--backend','cpu','--seed','42',*c['args'],c['input']]
                run=timed_run(cmd,ROOT/RAW/f'{c["id"]}-{rep}-{label}',env=clean_env(),timeout=600)
                assert run['exit_code']==0
                compare_output(Path(c['oracle']).read_bytes(),Path(run['output']).read_bytes())
                run.update(label=label,case=c['id'],repeat=rep,exact=True,cpu_seconds=run['user_seconds']+run['system_seconds']);r['runs'].append(run);save(REPORT,r)
                print(c['id'],rep,label,round(run['wall_seconds'],3),flush=True)
    r['summary']={c['id']:{label:{key:statistics.median(x[key] for x in r['runs'] if x['case']==c['id'] and x['label']==label and x['repeat']>0) for key in ['wall_seconds','cpu_seconds','peak_rss_kib']} for label in r['variants']} for c in cases}
    r['status']='screened';save(REPORT,r);print(json.dumps(r['summary']),flush=True)
if __name__=='__main__':
    os.chdir(ROOT);p=argparse.ArgumentParser();p.add_argument('action',choices=['build','screen']);globals()[p.parse_args().action]()
