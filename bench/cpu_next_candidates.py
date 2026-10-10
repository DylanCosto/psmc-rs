#!/usr/bin/env python3
"""Isolated v0.3.2 register-width and overhead experiments; no production edits."""
import argparse, io, json, os, shutil, statistics, subprocess, tarfile
from pathlib import Path
from common import ROOT, save, sha256, timed_run
from phase2_common import clean_env
from phase1_differential import compare_output
from cpu_campaign_kernel_variants import replace
BASE='4ab9ff5'
HASH='24d47084c2914aa44109040b7f5593efb7353621cb0d36ccdb28cd1a060f4c83'
RAW=Path('work/cpu-next/candidates')
REPORT='bench/cpu-next-screen.json'
LABELS=['counts32s8','counts32s4','messages32','noreserve','dispatch']

def function_replace(path,name,code):
    s=path.read_text();start=s.index('    #[target_feature(enable = "avx")]\n    pub(super) unsafe fn '+name+'(')
    end=s.index('    #[target_feature(enable = "avx")]',start+10)
    path.write_text(s[:start]+code+'\n'+s[end:])

def counts(path,sites):
    lines=['    #[target_feature(enable = "avx")]', '    pub(super) unsafe fn counts_sequence64(counts: &mut [f64], observations: &[u8], forward: &[f64], backward: &[f64], products: &[f64]) {',
      '        // SAFETY: wrapper checks 64-state shapes and symbols; l+31<=63.',
      '        // Every cell adds sites in original order, with two unfused multiplies.',
      '        unsafe {',f'            for begin in (1..observations.len()).step_by({sites}) {{',f'                let end = (begin + {sites}).min(observations.len());','                for k in 0..64 {','                    for l in (0..64).step_by(32) {']
    for j in range(8):lines.append(f'                        let mut sum{j} = _mm256_loadu_pd(counts.as_ptr().add(k*64+l+{4*j}));')
    lines+=['                        for u in begin..end {','                            let f = _mm256_set1_pd(*forward.get_unchecked(u*64+k));','                            let row = *observations.get_unchecked(u) as usize*4096+k*64+l;','                            let next = (u+1)*64+l;']
    for j in range(8):lines += [f'                            let first{j} = _mm256_mul_pd(f, _mm256_loadu_pd(products.as_ptr().add(row+{4*j})));',f'                            let term{j} = _mm256_mul_pd(first{j}, _mm256_loadu_pd(backward.as_ptr().add(next+{4*j})));',f'                            sum{j} = _mm256_add_pd(sum{j}, term{j});']
    lines+=['                        }']
    for j in range(8):lines.append(f'                        _mm256_storeu_pd(counts.as_mut_ptr().add(k*64+l+{4*j}),sum{j});')
    lines+=['                    }','                }','            }','        }','    }']
    function_replace(path,'counts_sequence64','\n'.join(lines))

def messages(path):
    for direction in ['forward','backward']:
        forward=direction=='forward';iterator,matrix,value=('previous','matrix','f') if forward else ('next','transpose','b')
        signature='out: &mut [f64], previous: &[f64], matrix: &[f64], emission: &[f64]' if forward else 'out: &mut [f64], next: &[f64], transpose: &[f64], scale: f64'
        lines=['    #[target_feature(enable = "avx")]',f'    pub(super) unsafe fn {direction}64({signature}) {{','        // SAFETY: wrapper checks exact 64-state dimensions; k+31<=63.', '        // Eight independent ordered chains; each lane adds l=0..64 unchanged.','        unsafe {','            for k in (0..64).step_by(32) {']
        for j in range(8):lines.append(f'                let mut sum{j} = _mm256_setzero_pd();')
        lines += [f'                for (l,&{value}) in {iterator}.iter().enumerate() {{',f'                    let v = _mm256_set1_pd({value});']
        for j in range(8):
            lines.append(f'                    let a{j} = _mm256_loadu_pd({matrix}.as_ptr().add(l*64+k+{j*4}));')
            prod=f'_mm256_mul_pd(v,a{j})' if forward else f'_mm256_mul_pd(a{j},v)'
            lines.append(f'                    sum{j} = _mm256_add_pd(sum{j},{prod});')
        lines.append('                }')
        for j in range(8):
            result=f'_mm256_mul_pd(_mm256_loadu_pd(emission.as_ptr().add(k+{j*4})),sum{j})' if forward else f'_mm256_div_pd(sum{j},_mm256_set1_pd(scale))'
            lines.append(f'                _mm256_storeu_pd(out.as_mut_ptr().add(k+{j*4}),{result});')
        lines+=['            }','        }','    }'];function_replace(path,direction+'64','\n'.join(lines))

def prepare(scratch,label):
    simd=scratch/'crates/psmc-cpu/src/simd.rs';lib=scratch/'crates/psmc-cpu/src/lib.rs'
    if label.startswith('counts32s'):counts(simd,int(label.removeprefix('counts32s')))
    elif label=='messages32':messages(simd)
    elif label=='noreserve':
        s=lib.read_text();start=s.index('        // Avoid amortized doubling');end=s.index('        messages.forward.resize',start);s=s[:start]+s[end:];start=s.index('\nfn reserve_messages(');s=s[:start]+'\n';lib.write_text(s)
        tests=scratch/'crates/psmc-cpu/src/tests.rs';s=tests.read_text();start=s.index('\n#[test]\nfn message_capacity_growth_preserves_values_and_reuses_storage()');tests.write_text(s[:start]+'\n')
    elif label=='dispatch':
        s=lib.read_text();start=s.index('        for u in 1..length {');end=s.index('        for (((count, &initial)',start);loop=s[start:end]
        loop=loop.replace('                if sequence_counts.is_none() {\n                    avx.counts(&mut counts.a, forward, product, next_backward);\n                }','                avx.counts(&mut counts.a, forward, product, next_backward);')
        new='''        if sequence_counts.is_some() {
            for u in 1..length {
                let forward = &messages.forward[u*n..][..n];
                let backward = &messages.backward[u*n..][..n];
                let scale = messages.scales[u];
                let emission_counts = &mut counts.e[observations[u-1] as usize*n..][..n];
                for ((count,&f),&b) in emission_counts.iter_mut().zip(forward).zip(backward) {
                    *count += f*b*scale;
                }
            }
        } else {
'''+loop+'        }\n';lib.write_text(s[:start]+new+s[end:])
    else:raise ValueError(label)

def build():
    os.chdir(ROOT);RAW.mkdir();assert sha256('work/cpu-next/baseline')==HASH
    report=dict(status='building',base_commit=BASE,runner_sha256=sha256(__file__),variants={'baseline':dict(binary='work/cpu-next/baseline',sha256=HASH)},runs=[])
    for label in LABELS:
        scratch=RAW/label;scratch.mkdir()
        data=subprocess.check_output(['git','archive',BASE,'Cargo.toml','Cargo.lock','rust-toolchain.toml','crates'])
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:tar.extractall(scratch,filter='data')
        prepare(scratch,label)
        commands=[['cargo','fmt','--all'],['cargo','test','--workspace','--offline'],['cargo','test','--workspace','--release','--offline'],['cargo','build','--release','--bins','--examples','--offline']]
        for i,cmd in enumerate(commands):
            with (scratch/f'build-{i}.log').open('w') as log:subprocess.run(cmd,cwd=scratch,env={**clean_env(),'CARGO_BUILD_JOBS':'16','RUST_TEST_THREADS':'16'},stdout=log,stderr=subprocess.STDOUT,check=True)
        binary=scratch/'target/release/psmc-rs';report['variants'][label]=dict(binary=str(binary),sha256=sha256(binary),source={str(p.relative_to(scratch)):sha256(p) for p in (scratch/'crates').rglob('*.rs')},commands=commands,logs=[dict(path=str(scratch/f'build-{i}.log'),sha256=sha256(scratch/f'build-{i}.log')) for i in range(4)])
        save(REPORT,report);print('Built and tested '+label,flush=True)
    report['status']='built';save(REPORT,report)

def screen():
    os.chdir(ROOT);r=json.loads(Path(REPORT).read_text());assert r['status']=='built'
    profile=json.loads(Path('bench/cpu-next-profile.json').read_text())
    cases=[x for x in profile['cases'] if x['id'] in ['hg-bootstrap01','k23-n30','bootstrap-00-k23-n30']]
    r['cases']=cases;r['screen_runner_sha256']=sha256(__file__)
    labels=list(r['variants'])
    for case in cases:
        assert sha256(case['input'])==case['input_sha256'];assert sha256(case['oracle'])==case['oracle_sha256']
        for repeat in range(4):
            order=labels[repeat:]+labels[:repeat]
            for label in order:
                entry=r['variants'][label];assert sha256(entry['binary'])==entry['sha256']
                out=ROOT/RAW/f'{case["id"]}-{repeat}-{label}'
                cmd=['taskset','-c','0',entry['binary'],'--backend','cpu','--simd','auto','--seed','42',*case['args'],case['input']]
                run=timed_run(cmd,out,env=clean_env(),timeout=600);assert run['exit_code']==0
                compare_output(Path(case['oracle']).read_bytes(),Path(run['output']).read_bytes())
                run.update(label=label,case=case['id'],repeat=repeat,kind='warmup' if repeat==0 else 'measurement',exact=True,cpu_seconds=run['user_seconds']+run['system_seconds']);r['runs'].append(run);save(REPORT,r)
                print(json.dumps({k:run[k] for k in ['case','label','repeat','wall_seconds','cpu_seconds']}),flush=True)
    r['summary']={c['id']:{label:{field:dict(median=statistics.median(v),minimum=min(v),maximum=max(v)) for field in ['wall_seconds','cpu_seconds','peak_rss_kib'] for v in [[x[field] for x in r['runs'] if x['case']==c['id'] and x['label']==label and x['repeat']>0]]} for label in labels} for c in cases}
    r['status']='passed';save(REPORT,r);print(json.dumps(r['summary']),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['build','screen']);globals()[p.parse_args().action]()
