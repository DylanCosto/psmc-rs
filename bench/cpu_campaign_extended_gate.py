#!/usr/bin/env python3
"""Check the final frozen CPU binary against all 66 predeclared new C cases."""
import json
import os
from pathlib import Path
import subprocess
from common import ROOT, save, sha256
from phase1_differential import compare_output
from phase2_common import clean_env, verify_binaries, utc_stamp
from phase3_common import resource_policy


def main():
    os.chdir(ROOT)
    policy=resource_policy()
    gate=json.loads(Path('bench/cpu-campaign-validation.json').read_text())
    assert gate['status']=='passed'
    provenance=gate['provenance'];verify_binaries(provenance)
    raw=Path('bench/cpu-campaign-final')/('extended-'+utc_stamp());raw.mkdir(parents=True)
    report=dict(status='running',resource_policy=policy,provenance=provenance,raw_directory=str(raw),runner_sha256=sha256(__file__),cases=[])
    dest='bench/cpu-campaign-extended.json'
    for source in ['bench/cpu-campaign-fixtures.json','bench/cpu-campaign-hmm-fixtures.json']:
        old=json.loads(Path(source).read_text());assert old['status']=='passed'
        verify_binaries(old['provenance'])
        for case in old['cases']:
            oracle=next(r for r in case['runs'] if r['label']=='vanilla')
            assert sha256(oracle['output'])==oracle['sha256']
            assert sha256(case['input'])==case['input_sha256']
            output=raw/(case['id']+'.psmc')
            command=[provenance['binaries']['candidate']['path'],'--backend','cpu','--simd','auto','--seed','42','-o',str(output),*oracle['command'][3:]]
            result=subprocess.run(command,env=clean_env(),capture_output=True)
            (raw/(case['id']+'.stderr')).write_bytes(result.stderr)
            assert result.returncode==0
            comparison=compare_output(Path(oracle['output']).read_bytes(),output.read_bytes())
            report['cases'].append(dict(id=case['id'],source_report=source,source_report_sha256=sha256(source),input_sha256=case['input_sha256'],command=command,output=str(output),output_sha256=sha256(output),oracle_sha256=oracle['sha256'],finite=not oracle['nonfinite'],comparison=comparison))
            save(dest,report)
    verify_binaries(provenance)
    assert len(report['cases'])==66
    report.update(status='passed',finite=sum(c['finite'] for c in report['cases']),pathology_controls=sum(not c['finite'] for c in report['cases']))
    save(dest,report)
    print(json.dumps({k:report[k] for k in ['status','finite','pathology_controls']}),flush=True)


if __name__=='__main__':main()
