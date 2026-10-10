"""Hoist uniform-symbol coefficients; preserve each ordered count recurrence."""
import argparse,io,json,os,statistics,subprocess,tarfile
from pathlib import Path
from common import ROOT,save,sha256,timed_run
from phase2_common import clean_env
from phase1_differential import compare_output
from cpu_next_candidates import function_replace
RAW=Path('work/relook/counts');REPORT='bench/relook-counts.json'

def generate(path,kb,width,maximum):
    source=path.read_text()
    start=source.index('    #[target_feature(enable = "avx")]\n    pub(super) unsafe fn counts_emissions64(')
    end=source.index('    #[target_feature(enable = "avx")]',start+10)
    original=source[start:end]
    inner=original.index('                for k in (0..64).step_by(2) {')
    emissions=original.index('                for u in begin..end {\n                    let z')
    fallback=original[inner:emissions]
    emission_body=original[emissions:original.rfind('            }')]
    prefix=original[:original.index('            for begin in')]
    lines=[prefix,'            let mut begin=1usize;', '            while begin<observations.len() {',
           '                let mut end=(begin+16).min(observations.len());',
           '                let z=observations[begin];',
           '                let uniform=observations[begin..end].iter().all(|&s|s==z);',
           '                if uniform {']
    if maximum>16:
        lines.append(f'                    while end<observations.len() && end<begin+{maximum} && observations[end]==z {{end+=1;}}')
    lines += [f'                    for k in (0..64).step_by({kb}) {{',f'                        for l in (0..64).step_by({width}) {{',
              '                            let row=z as usize*4096+k*64+l;']
    for a in range(kb):
        for j in range(width//4):
            lines += [f'                            let c{a}_{j}=_mm256_loadu_pd(products.as_ptr().add(row+{a*64+j*4}));',
                      f'                            let mut s{a}_{j}=_mm256_loadu_pd(counts.as_ptr().add((k+{a})*64+l+{j*4}));']
    lines += ['                            for u in begin..end {']
    for a in range(kb):lines.append(f'                                let f{a}=_mm256_set1_pd(*forward.get_unchecked(u*64+k+{a}));')
    for j in range(width//4):
        lines.append(f'                                let b{j}=_mm256_loadu_pd(backward.as_ptr().add((u+1)*64+l+{j*4}));')
        for a in range(kb):
            lines.append(f'                                s{a}_{j}=_mm256_add_pd(s{a}_{j},_mm256_mul_pd(_mm256_mul_pd(f{a},c{a}_{j}),b{j}));')
    lines+=['                            }']
    for a in range(kb):
        for j in range(width//4):lines.append(f'                            _mm256_storeu_pd(counts.as_mut_ptr().add((k+{a})*64+l+{j*4}),s{a}_{j});')
    lines+=['                        }','                    }','                } else {',fallback,'                }',emission_body,
            '                begin=end;','            }','        }','    }']
    function_replace(path,'counts_emissions64','\n'.join(lines))

def add_tests(path):
    # Independent scalar reference from the accepted gate, additional mixed runs.
    tests=Path('bench/exhaust_fusion_tests.rs').read_text().replace('mod fusion_tests','mod relook_run_tests')
    tests=tests.replace('for mask in 0..4','for mask in 0..7')
    tests=tests.replace('if mask==3 {(u%3) as u8}else{mask}',
        'if mask<3 {mask} else if mask==3 {(u%3) as u8} else {((u/[13,17,63][mask as usize-4])%3) as u8}')
    path.write_text(path.read_text()+tests)

def build():
    RAW.mkdir(parents=True)
    r=dict(status='building',base='30efe0b',runner_sha256=sha256(__file__),variants={},runs=[])
    configs={'baseline':None,'uniform16':(2,8,16),'uniform64':(2,8,64),'uniformwide':(1,16,16)}
    installed='bin/psmc-rs-v0.4.1'
    r['variants']['installed']=dict(binary=installed,sha256=sha256(installed))
    for label,config in configs.items():
        scratch=RAW/label;scratch.mkdir()
        archive=subprocess.check_output(['git','archive','30efe0b','Cargo.toml','Cargo.lock','rust-toolchain.toml','crates'])
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(scratch,filter='data')
        p=scratch/'crates/psmc-cpu/src/simd.rs'
        if config:generate(p,*config)
        add_tests(p)
        commands=[['cargo','fmt','--all'],['cargo','test','--workspace','--release','--locked','--offline'],['cargo','build','--release','--locked','--offline','--bins','--examples']]
        for i,cmd in enumerate(commands):
            with (scratch/f'build-{i}.log').open('w') as log:subprocess.run(cmd,cwd=scratch,env=clean_env(),stdout=log,stderr=subprocess.STDOUT,check=True)
        binary=scratch/'target/release/psmc-rs'
        r['variants'][label]=dict(binary=str(binary),sha256=sha256(binary),config=config,commands=commands,
            source={str(p.relative_to(scratch)):sha256(p) for p in (scratch/'crates').rglob('*.rs')})
        save(REPORT,r);print('built',label,flush=True)
    r['status']='built';save(REPORT,r)

def screen():
    r=json.load(open(REPORT));assert r['status']=='built'
    cases=[c for c in json.load(open('bench/cuda-profile.json'))['cases'] if c['id'] in ['hg-bootstrap01','k23-n30']]
    r['cases']=[{k:v for k,v in c.items() if k not in ['runs','cpu_seconds_medians']} for c in cases]
    for c in cases:
        assert sha256(c['input'])==c['input_sha256'] and sha256(c['oracle'])==c['oracle_sha256']
        for rep in range(4):
            labels=list(r['variants']);labels=labels[rep:]+labels[:rep]
            for label in labels:
                v=r['variants'][label];assert sha256(v['binary'])==v['sha256']
                cmd=['taskset','-c','0',v['binary'],'--backend','cpu','--seed','42',*c['args'],c['input']]
                run=timed_run(cmd,ROOT/RAW/f'{c["id"]}-{rep}-{label}',env=clean_env(),timeout=600);assert run['exit_code']==0
                run.update(label=label,repeat=rep,case=c['id'],comparison=compare_output(Path(c['oracle']).read_bytes(),Path(run['output']).read_bytes()),cpu_seconds=run['user_seconds']+run['system_seconds'])
                r['runs'].append(run);save(REPORT,r);print(c['id'],rep,label,run['wall_seconds'],flush=True)
    r['summary']={c['id']:{label:{key:statistics.median(x[key] for x in r['runs'] if x['case']==c['id'] and x['label']==label and x['repeat']>0) for key in ['wall_seconds','cpu_seconds','peak_rss_kib']} for label in r['variants']} for c in cases}
    r['status']='screened';save(REPORT,r);print(r['summary'],flush=True)

if __name__=='__main__':
    os.chdir(ROOT);p=argparse.ArgumentParser();p.add_argument('action',choices=['build','screen']);globals()[p.parse_args().action]()
