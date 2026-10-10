"""Final frozen-binary/output/provenance audit for the optional CUDA milestone."""
import json,subprocess
from pathlib import Path
from common import ROOT,save,sha256
from phase1_differential import compare_output

def main():
    import os
    os.chdir(ROOT)
    report=dict(status='running',source_base_commit='0905ea0',source_sha256={str(p):sha256(p) for p in sorted(Path('crates').rglob('*')) if p.is_file()},configuration_sha256={str(p):sha256(p) for p in map(Path,['Cargo.toml','Cargo.lock','rust-toolchain.toml'])},runner_sha256=sha256(__file__),reports={},batch_outputs_rechecked=0)
    delivery=json.load(open('bench/cuda-delivery.json'));benchmark=json.load(open('bench/cuda-benchmark.json'));gate=json.load(open('bench/cuda-final-validation.json'))
    assert delivery['status']=='passed' and benchmark['status']=='passed' and gate['failed']==0 and gate['passed']==113
    expected=benchmark['binaries']['cuda']['sha256']
    for f in ['work/cuda/final-candidate','target/release/psmc-rs','bin/psmc-rs-cuda']:assert sha256(f)==expected
    baseline='f0c3282e87e3eed0cc31c63a438429c19ad47cedec4c56c1150cc8520838e305'
    for f in ['bin/psmc-rs','bin/psmc-rs-v0.3.3']:assert sha256(f)==baseline
    assert delivery['binary_sha256']==expected
    old=json.load(open('bench/cuda-validation.json'))
    assert sha256('work/cuda/initial-wrapper')==old['binaries']['candidate']['sha256']
    assert sha256('work/cuda/wrapper')==gate['binaries']['candidate']['sha256']
    references=json.load(open('bench/hg-benchmark.json'))['canonical_outputs']
    for run in benchmark['runs']:
        for i,reference in enumerate(references):
            assert sha256(reference['path'])==reference['sha256']
            actual=Path('work/cuda/batches')/run['label']/f'replicate-{i:02}.psmc'
            comparison=compare_output(Path(reference['path']).read_bytes(),actual.read_bytes())
            assert comparison==run['comparisons'][i]
            report['batch_outputs_rechecked']+=1
    assert report['batch_outputs_rechecked']==360
    for case in delivery['extended']:
        from phase1_differential import strict_output
        import hashlib
        actual=hashlib.sha256(strict_output(Path(case['output']).read_bytes())[0]).hexdigest()
        assert actual==case['comparison']['compared_sha256']
    for case in delivery['human']:assert sha256(case['output'])==case['output_sha256']
    assert len(delivery['extended'])==66 and len(delivery['human'])==2 and len(delivery['controls'])==9
    assert not benchmark['performance_promotion_gate']
    for p in sorted(Path('bench').glob('cuda-*.json')):
        if p.name!='cuda-audit.json':report['reports'][str(p)]=sha256(p)
    report.update(status='passed',cuda_binary_sha256=expected,cpu_binary_preserved_sha256=baseline,extended_outputs_rechecked=66,human_outputs_rechecked=2,delivery_decision='CUDA hybrid is exact on tested stack but slower; keep experimental opt-in and recommend v0.3.3 CPU.',scope_limits=['Other GPUs, platforms and whole genomes not_run.','No speedup claimed from diagnostic kernel/single-fit timings.'])
    save('bench/cuda-audit.json',report);print(json.dumps({k:v for k,v in report.items() if k not in ['source_sha256','configuration_sha256','reports']}),flush=True)
if __name__=='__main__':main()
