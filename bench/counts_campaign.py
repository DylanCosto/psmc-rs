#!/usr/bin/env python3
"""Reproducible isolated candidates and full-fit screens for ordered K64 counts."""
import argparse
import io
import tarfile
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
from common import ROOT, save, sha256, timed_run, nonfinite_records
from phase2_common import clean_env, source_hashes
from phase1_differential import compare_output
from hg_benchmark import ARGS

BASE_COMMIT = 'bdd1a4309502251f78ced5085f5d7aa498a200de'
BASE = 'b0fc39d7c31637221de1152fc0d502bb65c90d0a5b9d6672250fe3117f75bfa4'
RAW = Path('work/counts-campaign')
REPORT = 'bench/counts-screen.json'

def replace(path, old, new):
    s=path.read_text(); assert s.count(old)==1, (str(path),old[:80]);path.write_text(s.replace(old,new))

def memory(scratch):
    p=scratch/'crates/psmc-cpu/src/lib.rs'
    replace(p, '        messages.forward.resize(cells, 0.0);', '''        // Avoid amortized doubling when a later bootstrap block is slightly larger.
        // reserve_exact changes capacity only; resize and all arithmetic stay ordered.
        reserve_messages(&mut messages.forward, cells);
        reserve_messages(&mut messages.backward, cells);
        reserve_messages(&mut messages.scales, rows);
        messages.forward.resize(cells, 0.0);''')
    with p.open('a') as f:f.write('''
fn reserve_messages(buffer: &mut Vec<f64>, needed: usize) {
    if needed > buffer.capacity() {
        buffer.reserve_exact(needed - buffer.len());
    }
}
''')
    with (scratch/'crates/psmc-cpu/src/tests.rs').open('a') as f:f.write('''
#[test]
fn message_capacity_growth_preserves_values_and_reuses_storage() {
    let mut buffer = vec![0.0, -0.0, f64::from_bits(1)];
    reserve_messages(&mut buffer, 4);
    assert_eq!(buffer.len(), 3);
    same_slice(&buffer, &[0.0, -0.0, f64::from_bits(1)]);
    buffer.resize(4, 0.0);
    let capacity = buffer.capacity();
    let pointer = buffer.as_ptr();
    buffer.truncate(1);
    reserve_messages(&mut buffer, capacity);
    assert_eq!(buffer.as_ptr(), pointer);
    assert_eq!(buffer.capacity(), capacity);
    reserve_messages(&mut buffer, capacity + 1);
    assert!(buffer.capacity() >= capacity + 1);
    assert_eq!(buffer.len(), 1);
    same_float(buffer[0], 0.0);
}
''')

def fixed(scratch):
    p=scratch/'crates/psmc-cpu/src/simd.rs'
    replace(p, '            x86::counts(counts, forward, product, next)', '''            if n == 64 {
                x86::counts64(counts, forward, product, next)
            } else {
                x86::counts(counts, forward, product, next)
            }''')
    code='''    #[target_feature(enable = "avx")]
    pub(super) unsafe fn counts64(counts: &mut [f64], forward: &[f64], product: &[f64], next: &[f64]) {
        // SAFETY: caller validates all four slices for exactly 64 states.
        unsafe {
            for k in 0..64 {
                let f = _mm256_set1_pd(*forward.get_unchecked(k));
                for l in (0..64).step_by(16) {
'''
    for j in range(4):
        off=f'k * 64 + l + {j*4}'
        code+=f'''                    let first{j} = _mm256_mul_pd(f, _mm256_loadu_pd(product.as_ptr().add({off})));
                    let term{j} = _mm256_mul_pd(first{j}, _mm256_loadu_pd(next.as_ptr().add(l + {j*4})));
                    let old{j} = _mm256_loadu_pd(counts.as_ptr().add({off}));
                    _mm256_storeu_pd(counts.as_mut_ptr().add({off}), _mm256_add_pd(old{j}, term{j}));
'''
    code+='''                }
            }
        }
    }

'''
    replace(p,'    #[target_feature(enable = "avx")]\n    pub(super) unsafe fn counts(',code+'    #[target_feature(enable = "avx")]\n    pub(super) unsafe fn counts(')

def tile(scratch,size):
    p=scratch/'crates/psmc-cpu/src/simd.rs'
    wrapper='''    pub(crate) fn counts_sequence64(self, counts: &mut [f64], observations: &[u8], forward: &[f64], backward: &[f64], products: &[f64]) {
        assert!(!observations.is_empty());
        assert!(observations.iter().all(|&z| z <= 2));
        let cells = observations.len().checked_add(1).and_then(|r| r.checked_mul(64)).expect("message size overflow");
        assert_eq!(counts.len(), 4096);
        assert_eq!(products.len(), 3 * 4096);
        assert_eq!(forward.len(), cells);
        assert_eq!(backward.len(), cells);
        #[cfg(target_arch = "x86_64")]
        // SAFETY: capability checks AVX; validated exact dimensions and symbols
        // bound every complete 4-lane load/store. Tiles never add HMM boundaries.
        unsafe { x86::counts_sequence64(counts, observations, forward, backward, products) }
        #[cfg(not(target_arch = "x86_64"))]
        unreachable!("AVX capability is never constructed on this architecture");
    }

'''
    replace(p,'    pub(crate) fn counts(self,',wrapper+'    pub(crate) fn counts(self,')
    code='''    #[target_feature(enable = "avx")]
    pub(super) unsafe fn counts_sequence64(counts: &mut [f64], observations: &[u8], forward: &[f64], backward: &[f64], products: &[f64]) {
        // Each lane carries its existing count through ascending sites. There is
        // no partial sum or horizontal reduction; (f * ae) * b remains unfused.
        // SAFETY: the capability wrapper validates dimensions and symbols.
        unsafe {
'''+f'            for begin in (1..observations.len()).step_by({size}) {{\n                let end = (begin + {size}).min(observations.len());\n'+'''                for k in 0..64 {
                    for l in (0..64).step_by(16) {
'''
    for j in range(4):code+=f'                        let mut sum{j} = _mm256_loadu_pd(counts.as_ptr().add(k * 64 + l + {j*4}));\n'
    code+='''                        for u in begin..end {
                            let f = _mm256_set1_pd(*forward.get_unchecked(u * 64 + k));
                            let row = *observations.get_unchecked(u) as usize * 4096 + k * 64 + l;
                            let next = (u + 1) * 64 + l;
'''
    for j in range(4):code+=f'''                            let first{j} = _mm256_mul_pd(f, _mm256_loadu_pd(products.as_ptr().add(row + {j*4})));
                            let term{j} = _mm256_mul_pd(first{j}, _mm256_loadu_pd(backward.as_ptr().add(next + {j*4})));
                            sum{j} = _mm256_add_pd(sum{j}, term{j});
'''
    code+='                        }\n'
    for j in range(4):code+=f'                        _mm256_storeu_pd(counts.as_mut_ptr().add(k * 64 + l + {j*4}), sum{j});\n'
    code+='''                    }
                }
            }
        }
    }

'''
    replace(p,'    #[target_feature(enable = "avx")]\n    pub(super) unsafe fn counts(',code+'    #[target_feature(enable = "avx")]\n    pub(super) unsafe fn counts(')
    with p.open('a') as f:f.write('''
#[cfg(test)]
mod sequence_tests {
    use super::*;
    #[test]
    fn ordered_counts64_match_scalar_at_tile_boundaries_and_extremes() {
        let Some(avx) = Avx::select(SimdMode::Auto, 64).unwrap() else { return; };
        let values = [0.0, -0.0, f64::from_bits(1), -f64::from_bits(1), 1e-300, 1e300, 0.1, -1.0, f64::INFINITY, f64::NEG_INFINITY, f64::NAN];
        for length in [1, 2, 7, 8, 9, 15, 16, 17, 31, 32, 33, 63, 64, 65, 129] {
            for extreme in [false, true] {
                let cells = (length + 1) * 64;
                let make = |count: usize, salt: usize| -> Vec<f64> {
                    (0..count).map(|i| if extreme { values[(i * 7 + salt) % values.len()] } else { ((i * 17 + salt) % 103) as f64 / 107.0 }).collect()
                };
                // Offset all arrays to exercise unaligned vector loads/stores.
                let f = make(cells + 1, 1); let b = make(cells + 1, 3); let products = make(3 * 4096 + 1, 7);
                let obs: Vec<u8> = (0..length).map(|u| (u % 3) as u8).collect();
                let mut expected = vec![1e-25; 4096];
                for u in 1..length { for k in 0..64 { for l in 0..64 {
                    expected[k*64+l] += (f[1+u*64+k] * products[1+obs[u] as usize*4096+k*64+l]) * b[1+(u+1)*64+l];
                } } }
                let mut actual = vec![1e-25; 4097];
                avx.counts_sequence64(&mut actual[1..], &obs, &f[1..], &b[1..], &products[1..]);
                for (a, e) in actual[1..].iter().zip(expected) {
                    if e.is_nan() { assert!(a.is_nan()); } else { assert_eq!(a.to_bits(), e.to_bits()); }
                }
            }
        }
    }
    #[test]
    fn sequence_shape_and_symbol_errors_are_rejected() {
        let Some(avx) = Avx::select(SimdMode::Auto, 64).unwrap() else { return; };
        for (obs, cells, products, counts) in [(vec![],64,12288,4096), (vec![3],128,12288,4096), (vec![0],127,12288,4096), (vec![0],128,12287,4096), (vec![0],128,12288,4095)] {
            assert!(std::panic::catch_unwind(|| avx.counts_sequence64(&mut vec![0.0; counts], &obs, &vec![0.0; cells], &vec![0.0; cells], &vec![0.0; products])).is_err());
        }
    }
}
''')
    lib=scratch/'crates/psmc-cpu/src/lib.rs'
    replace(lib,'        counts.q0 = 0.0;\n        for u in 1..length {','''        counts.q0 = 0.0;
        let sequence_counts = self.avx.filter(|_| n == 64);
        if let Some(avx) = sequence_counts {
            avx.counts_sequence64(&mut counts.a, observations, &messages.forward,
                &messages.backward, &prepared.emission_transition);
        }
        for u in 1..length {''')
    replace(lib,'                avx.counts(&mut counts.a, forward, product, next_backward);','''                if sequence_counts.is_none() {
                    avx.counts(&mut counts.a, forward, product, next_backward);
                }''')

def baseline_sources(scratch):
    archive=subprocess.check_output(['git','archive',BASE_COMMIT,'Cargo.toml','Cargo.lock','rust-toolchain.toml','crates'])
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar: tar.extractall(scratch,filter='data')


def verify_generator():
    os.chdir(ROOT);report=json.loads(Path(REPORT).read_text());checks=[]
    for label in ['memory','fixed64','tile8','tile32']:
        scratch=RAW/('regenerated-'+label);scratch.mkdir()
        baseline_sources(scratch);memory(scratch)
        if label=='fixed64':fixed(scratch)
        if label.startswith('tile'):tile(scratch,int(label[4:]))
        subprocess.run(['cargo','fmt','--all'],cwd=scratch,check=True)
        actual={str(p.relative_to(scratch)):sha256(p) for p in (scratch/'crates').rglob('*.rs')}
        assert actual==report['variants'][label]['source']
        checks.append(dict(label=label,all_source_hashes_match=True))
    save('bench/counts-generator.json',dict(status='passed',baseline_commit=BASE_COMMIT,runner_sha256=sha256(__file__),screen_report_sha256=sha256(REPORT),checks=checks))


def build():
    os.chdir(ROOT)
    original=Path('bin/psmc-rs-v0.3.1') if Path('bin/psmc-rs-v0.3.1').exists() else Path('bin/psmc-rs')
    assert sha256(original)==BASE
    RAW.mkdir(parents=True,exist_ok=True)
    baseline=RAW/'baseline'; assert not baseline.exists();shutil.copy2(original,baseline)
    report=dict(status='building',baseline_commit=BASE_COMMIT,baseline_source={p:__import__('hashlib').sha256(subprocess.check_output(['git','show',BASE_COMMIT+':'+p])).hexdigest() for p in source_hashes()},runner_sha256=sha256(__file__),variants={'baseline':dict(binary=str(baseline),sha256=BASE)},runs=[])
    save(REPORT,report)
    for label in ['memory','fixed64','tile8','tile32']:
        scratch=RAW/label;scratch.mkdir()
        baseline_sources(scratch)
        memory(scratch)
        if label=='fixed64':fixed(scratch)
        if label.startswith('tile'):tile(scratch,int(label[4:]))
        commands=[['cargo','fmt','--all'],['cargo','test','--workspace','--offline'],['cargo','test','--workspace','--release','--offline'],['cargo','build','--release','--bins','--examples','--offline']]
        for i,command in enumerate(commands):
            with (scratch/f'build-{i}.log').open('w') as log:subprocess.run(command,cwd=scratch,env={**clean_env(),'CARGO_BUILD_JOBS':'16','RUST_TEST_THREADS':'16'},stdout=log,stderr=subprocess.STDOUT,check=True)
        binary=scratch/'target/release/psmc-rs'
        report['variants'][label]=dict(binary=str(binary),sha256=sha256(binary),commands=commands,source={str(p.relative_to(scratch)):sha256(p) for p in (scratch/'crates').rglob('*.rs')},logs=[dict(path=str(scratch/f'build-{i}.log'),sha256=sha256(scratch/f'build-{i}.log')) for i in range(len(commands))])
        save(REPORT,report);print('Built and tested '+label,flush=True)
    report['status']='built';save(REPORT,report)

def screen():
    os.chdir(ROOT);report=json.loads(Path(REPORT).read_text());assert report['status']=='built'
    manifest=json.loads(Path('bench/hg-input.json').read_text())
    old=json.loads(Path('bench/hg-benchmark.json').read_text())
    inp=manifest['replicates'][1];oracle=old['canonical_outputs'][1]
    assert sha256(inp['path'])==inp['sha256'];assert sha256(oracle['path'])==oracle['sha256']
    labels=list(report['variants']); report['input']=inp;report['oracle']=oracle
    report['screen_runner_sha256']=sha256(__file__)
    report['affinity']=sorted(os.sched_getaffinity(0));report['nice']=os.nice(0)
    # One discarded warmup per candidate, then three rotated complete N30 fits.
    for repeat in range(4):
        order=labels[repeat:]+labels[:repeat]
        for label in order:
            entry=report['variants'][label];assert sha256(entry['binary'])==entry['sha256']
            base=ROOT/RAW/f'screen-{repeat}-{label}'
            command=[entry['binary'],'--backend','cpu','--simd','auto',*ARGS,inp['path']]
            run=timed_run(command,base,env=clean_env(),timeout=600)
            run['cpu_seconds']=run['user_seconds']+run['system_seconds']
            assert run['exit_code']==0
            output=base.with_suffix('.psmc')
            compare_output(Path(oracle['path']).read_bytes(),output.read_bytes());assert not nonfinite_records(output.read_text())
            run.update(label=label,repeat=repeat,kind='warmup' if repeat==0 else 'measurement',exact=True,output_sha256=sha256(output))
            report['runs'].append(run);save(REPORT,report);print(json.dumps(run),flush=True)
    report['summary']={label:{field:dict(median=statistics.median(vals),minimum=min(vals),maximum=max(vals)) for field in ['wall_seconds','cpu_seconds','peak_rss_kib'] for vals in [[r[field] for r in report['runs'] if r['label']==label and r['repeat']>0]]} for label in labels}
    report['status']='passed';save(REPORT,report);print(json.dumps(report['summary']),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['build','screen','verify_generator']);o=p.parse_args();globals()[o.action]()
