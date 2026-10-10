#!/usr/bin/env python3
"""Fresh v0.3.3 attribution in an isolated copy; exact outputs required."""
import json,os,shutil,subprocess,statistics
from pathlib import Path
from common import ROOT,save,sha256,timed_run
from phase2_common import source_hashes,clean_env
from phase1_differential import compare_output

def main():
    os.chdir(ROOT);raw=Path('work/cuda/profile');raw.mkdir();scratch=raw/'source';scratch.mkdir()
    before=source_hashes()
    for f in ['Cargo.toml','Cargo.lock','rust-toolchain.toml']:shutil.copy2(f,scratch/f)
    shutil.copytree('crates',scratch/'crates')
    old=json.loads(Path('bench/cpu-campaign-final-profile.json').read_text())
    injection=json.loads((Path(old['raw_directory'])/'instrumentation.json').read_text())
    for c in injection['injections']:
        p=scratch/c['file'];s=p.read_text();assert s.count(c['old'])==1;p.write_text(s.replace(c['old'],c['new']))
    module=Path('bench/cpu_campaign_profile.rs').read_text().replace('[&str; 12]','[&str; 14]').replace('"iteration_inclusive"]','"iteration_inclusive", "transition_counts64", "emissions_and_other_counts"]').replace('[u64; 12]','[u64; 14]').replace('[0; 12]','[0; 14]')
    (scratch/injection['module']).write_text(module)
    p=scratch/'crates/psmc-cpu/src/lib.rs';s=p.read_text();oldtoken='        if let Some(avx) = sequence_counts {'
    assert s.count(oldtoken)==1;s=s.replace(oldtoken,oldtoken+'\n            let _counts_timer = psmc_core::diagnostic_profile::Guard::new(12);')
    token='        for u in 1..length {';assert s.count(token)==1;s=s.replace(token,'        let emission_diagnostic_start = psmc_core::diagnostic_profile::now();\n'+token)
    token='        psmc_core::diagnostic_profile::record(9, diagnostic_start);';s=s.replace(token,'        psmc_core::diagnostic_profile::record(13, emission_diagnostic_start);\n'+token);p.write_text(s)
    command=['cargo','build','--release','--locked','--offline','--jobs','16']
    with (raw/'build.log').open('w') as log:subprocess.run(command,cwd=scratch,env=clean_env(),stdout=log,stderr=subprocess.STDOUT,check=True)
    binary=str(scratch/'target/release/psmc-rs')
    cases=[dict(id='hg-unsplit',input='work/hg-input/NA12878_chr22.psmcfa',oracle='bench/hg/pilot/vanilla.psmc',args=['-p','4+25*2+4+6','-N','30','-t','15','-r','5','-I','0']),dict(id='hg-bootstrap01',input='work/hg-input/bootstrap-01.psmcfa',oracle=json.loads(Path('bench/hg-benchmark.json').read_text())['canonical_outputs'][1]['path'],args=['-p','4+25*2+4+6','-N','30','-t','15','-r','5','-I','0'])]
    for case in old['cases']:
        if case['id'] in ['k23-n30','bootstrap-00-k23-n30']:
            cases.append(dict(id=case['id'],input=case['input'],args=case['args'],oracle=str(Path(old['raw_directory'])/(case['id']+'-vanilla.psmc'))))
    report=dict(status='running',source_sha256=before,baseline_sha256=sha256('bin/psmc-rs-v0.3.3'),instrumented_binary_sha256=sha256(binary),source_injection_reference=sha256(Path(old['raw_directory'])/'instrumentation.json'),instrumented_sources={str(p.relative_to(scratch)):sha256(p) for p in (scratch/'crates').rglob('*.rs')},build_command=command,runner_sha256=sha256(__file__),cases=[],limitations=['Diagnostic only; not release timing. Inclusive sections overlap children.','Three repetitions pinned to CPU 0. No hardware-counter availability assumed.','transition_counts64 is a child of counts; emissions_and_other_counts includes all counts for non-K64 paths.'])
    for case in cases:
        runs=[]
        for rep in range(3):
            out=ROOT/raw/f'{case["id"]}-{rep}';profile=out.with_suffix('.profile.json')
            cmd=['taskset','-c','0',binary,'--backend','cpu','--simd','auto','--seed','42',*case['args'],case['input']]
            run=timed_run(cmd,out,env={**clean_env(),'PSMC_CPU_DIAGNOSTIC':str(profile)},timeout=1800);assert run['exit_code']==0
            run['comparison']=compare_output(Path(case['oracle']).read_bytes(),Path(run['output']).read_bytes())
            run['profile']=json.loads(profile.read_text());runs.append(run)
        report['cases'].append(dict(**case,input_sha256=sha256(case['input']),oracle_sha256=sha256(case['oracle']),runs=runs,cpu_seconds_medians={k:statistics.median(r['profile']['sections'][k]['nanoseconds']/1e9 for r in runs) for k in runs[0]['profile']['sections']}))
        save('bench/cuda-profile.json',report);print(json.dumps({case['id']:report['cases'][-1]['cpu_seconds_medians']}),flush=True)
    assert source_hashes()==before;report['status']='passed';save('bench/cuda-profile.json',report)
if __name__=='__main__':main()
