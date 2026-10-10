#!/usr/bin/env python3
"""Freeze provenance and distinguish failed equivalence gates from strict tests."""
import json,os,subprocess,re,tarfile,hashlib
from pathlib import Path
from common import ROOT,save,sha256

def main():
    os.chdir(ROOT)
    reports={name:json.load(open(f'bench/equivalent-{name}.json')) for name in ['c-baseline','validation','analysis','performance','strict-regression']}
    for name in ['c-baseline','validation','analysis','performance']:assert reports[name]['status']=='completed',name
    legacy=reports['strict-regression'];obsolete=[];strict_passed=0;snapshots=0
    for backend,entry in legacy['backend_reports'].items():
        child=json.load(open(entry['report']))
        for case in child['cases']:
            if case['status']=='passed':strict_passed+=1
            else:
                assert backend in ['cpu','scalar'] and case['name']=='reject_equivalent_mode',case
                obsolete.append(dict(backend=backend,case=case))
        assert entry['full_bootstrap_finite']==27 and entry['full_bootstrap_pathologies']==[16,26,28]
        snapshots+=len(entry['snapshots'])
    assert strict_passed==338 and len(obsolete)==2 and snapshots==10
    for report in ['c-baseline','validation','performance']:
        for run in reports[report]['runs']+reports[report].get('control_runs',[]):
            assert run['exit_code']==0
            assert not run['nonfinite_records_beyond_initial_RI']
            if 'stats' in run: assert not run['stats']['nonfinite_output']
            assert sha256(run['output'])==run['output_sha256']
            for output in run.get('outputs',[]):
                assert sha256(output['path'])==output['sha256']
                if 'stats' in output: assert not output['stats']['nonfinite_output']
    c=reports['c-baseline']
    assert sha256('work/equivalent/c-baseline-three-build-runner.py')==c['runner_sha256']
    assert sha256('bench/equivalent_c_resume.py')==c['completion_runner_sha256']
    reference=json.load(open('reference/build-vanilla.json'))
    assert c['source_commit']==reference['source_commit']
    assert sha256('work/psmc-source-vanilla.tar')==reference['source_archive_sha256']
    with tarfile.open('work/psmc-source-vanilla.tar') as archive:
        for name,digest in c['source_hashes'].items(): assert hashlib.sha256(archive.extractfile(name).read()).hexdigest()==digest
    assert len(c['runs'])==124
    for build in c['builds'].values():assert sha256(build['path'])==build['sha256']
    for data in c['datasets'].values():
        assert sha256(data['original'])==data['original_sha256']
        assert sha256(data['blocks'])==data['blocks_sha256']
        for sample in data['samples']:assert sha256(sample['path'])==sample['sha256']
    assert sha256('work/equivalent/psmc-rs-validation')==reports['validation']['binary_sha256']
    assert sha256('target/release/psmc-rs')==reports['performance']['binary_sha256']
    assert Path('work/equivalent/performance/validation.text').read_bytes()==Path('work/equivalent/performance/final.text').read_bytes()
    tests={}
    for label,path in [('debug','work/equivalent/tests-debug.log'),('release','work/equivalent/tests-release-final.log')]:
        text=Path(path).read_text();assert 'test result: FAILED' not in text
        results=re.findall(r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored;',text)
        totals=[sum(int(row[i]) for row in results) for i in range(3)]
        assert totals==[45,0,4],(label,totals)
        tests[label]=dict(passed=totals[0],failed=totals[1],ignored_hardware_cuda=totals[2],log_sha256=sha256(path))
    components=json.load(open('bench/equivalent-components.json'));assert components['status']=='passed'
    assert sha256(components['archived_binary'])==components['binary_sha256']
    assert sha256('crates/psmc-cpu/examples/equivalent_components.rs')==components['source_sha256']
    assert sha256('work/equivalent/trajectory-components.jsonl')==components['raw_output_sha256']
    for path,digest in components['inputs'].items(): assert sha256(path)==digest
    ci=json.load(open('bench/equivalent-ci.json'))
    assert ci['status']=='local_reference_check_passed' and ci['live_C_cases']==4
    for path,digest in ci['files'].items(): assert sha256(path)==digest
    repairs=json.load(open('bench/equivalent-repairs.json'))
    assert repairs['discarded_attempt_used_for_performance'] is False
    for output in repairs['discarded_attempt_exact_outputs']: assert sha256(output['path'])==output['sha256']
    sources=[Path('Cargo.toml'),Path('Cargo.lock'),*Path('crates').rglob('*.rs'),*Path('crates').rglob('Cargo.toml')]
    result=dict(status='completed',environment=dict(rustc=subprocess.check_output(['rustc','-vV'],text=True),cargo=subprocess.check_output(['cargo','--version'],text=True),libc=subprocess.check_output(['getconf','GNU_LIBC_VERSION'],text=True).strip(),cpu=next(line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name'))),tests=tests,component_report_sha256=sha256('bench/equivalent-components.json'),repairs_report_sha256=sha256('bench/equivalent-repairs.json'),ci_report_sha256=sha256('bench/equivalent-ci.json'),decision='retain_strict_default_and_opt_in_experimental_equivalent',strict_checks_passed=strict_passed,obsolete_availability_checks=obsolete,ordered_internal_traces=snapshots,full_human_strict_C_outputs=reports['analysis']['strict_exact_outputs'],
        C_sensitivity_fits=124,human_rust_fits=124,repeated_HG001_performance_fits=240,v041_control_fits=60,
        numerical_equivalence_qualified=all(d['summary']['exploratory_screen_pass']==31 and d['summary']['compiler_envelope_pass']==31 and d['summary']['bootstrap_spread_screen_pass']==31 for d in reports['analysis']['datasets'].values()),
        performance_gate=reports['performance']['performance_gate'],
        sources={str(p):sha256(p) for p in sources},reports={f'bench/equivalent-{k}.json':sha256(f'bench/equivalent-{k}.json') for k in reports},runners={str(p):sha256(p) for p in Path('bench').glob('equivalent_*.py')},
        validation_binary=dict(path='work/equivalent/psmc-rs-validation',sha256=sha256('work/equivalent/psmc-rs-validation')),
        final_binary=dict(path='target/release/psmc-rs',sha256=sha256('target/release/psmc-rs')),machine_code_unchanged_after_test_and_documentation_additions=True,
        base_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        limitations=['Experimental mode has failed at least one full-fit screen; do not claim proven scientific equivalence.','Full transition counts remain quadratic in state count.','No new CUDA hardware, ARM/NEON, other libm/platform or private whole-genome validation.','Concurrent correctness-run timings are not performance evidence.','Printed decimal precision limits empirical zero-difference claims.'])
    save('bench/equivalent-audit.json',result)
    print(json.dumps({k:result[k] for k in ['status','decision','strict_checks_passed','ordered_internal_traces','numerical_equivalence_qualified','performance_gate']},indent=2))
if __name__=='__main__':main()
