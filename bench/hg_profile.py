#!/usr/bin/env python3
"""Reuse source-verified release instrumentation for human-input attribution."""
import json
import os
from pathlib import Path
import subprocess
from common import ROOT, save, sha256, timed_run
from phase2_common import clean_env, source_hashes
from phase1_differential import compare_output


def main():
    os.chdir(ROOT)
    previous=json.loads(Path('bench/cpu-campaign-final-profile.json').read_text())
    assert previous['status']=='passed'
    before=source_hashes()
    assert before==previous['provenance']['source_sha256_at_freeze']
    oldraw=Path(previous['raw_directory'])
    injection=json.loads((oldraw/'instrumentation.json').read_text())
    scratch=Path('work/cpu-profile-20261010T072419292205Z')
    for path in before:
        expected=Path(path).read_text()
        for change in injection['injections']:
            if change['file']==path:
                assert expected.count(change['old'])==1
                expected=expected.replace(change['old'],change['new'])
        assert (scratch/path).read_text()==expected, path
    assert sha256(scratch/injection['module'])==previous['module_sha256']
    binary=oldraw/'bin/diagnostic'
    assert sha256(binary)==previous['instrumented_binary_sha256']
    batches=json.loads(Path('bench/hg-benchmark.json').read_text())
    assert batches['status']=='passed'
    canonical=batches['canonical_outputs']
    evaluations={o['index']:sum(int(line.split()[1]) for line in Path(o['path']).read_text().splitlines() if line.startswith('IT\t')) for o in canonical}
    selected=max(evaluations,key=lambda i:(evaluations[i],-i))
    inputs=json.loads(Path('bench/hg-input.json').read_text())
    pilot=json.loads(Path('bench/hg-pilot.json').read_text())
    cases=[dict(name='unsplit',input=inputs['input'],oracle=pilot['runs'][0]['output']),dict(name=f'bootstrap-{selected:02d}',input=inputs['replicates'][selected]['path'],oracle=canonical[selected]['path'])]
    raw=Path('bench/hg/profile');raw.mkdir()
    report=dict(status='running',runner_sha256=sha256(__file__),reused_instrumentation_report='bench/cpu-campaign-final-profile.json',reused_report_sha256=sha256('bench/cpu-campaign-final-profile.json'),source_sha256=before,binary=str(binary),binary_sha256=sha256(binary),source_reconstruction_verified=True,selected_bootstrap=selected,selection='Maximum optimizer evaluations in the complete canonical bootstrap outputs, lowest index tie-break; selection is for diagnostic attribution only.',optimizer_evaluations=evaluations,cases=[],limitations=['Instrumented CPU time is diagnostic, not a release speed measurement.','Nested inclusive scopes overlap. Do not add expectation or main to their child scopes.','One diagnostic run per selected input; hardware counters remain unavailable.'])
    for case in cases:
        profile=raw/(case['name']+'.profile.json')
        command=[str(binary),'--backend','cpu','--simd','auto','--seed','20261012',*batches['args'],case['input']]
        run=timed_run(command,(ROOT/raw/case['name']),env={**clean_env(),'PSMC_CPU_DIAGNOSTIC':str(profile)},timeout=1800)
        assert run['exit_code']==0
        comparison=compare_output(Path(case['oracle']).read_bytes(),Path(run['output']).read_bytes())
        report['cases'].append(dict(**case,run=run,profile=json.loads(profile.read_text()),comparison=comparison))
        save('bench/hg-profile.json',report)
        print(case['name']+' diagnostic exactness passed',flush=True)
    assert source_hashes()==before
    report['status']='passed';save('bench/hg-profile.json',report)

if __name__=='__main__': main()
