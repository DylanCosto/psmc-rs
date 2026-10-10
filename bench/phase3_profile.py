#!/usr/bin/env python3
"""Separately instrument E/M sections; never run with throughput benchmarks."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import os
import subprocess
from phase2_common import clean_env, verify_binaries
from phase1_differential import compare_output

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    os.chdir(ROOT)
    from phase3_common import resource_policy
    policy = resource_policy()
    gate = json.loads(Path('bench/phase-3-validation.json').read_text())
    assert gate['status'] == 'passed'
    provenance = gate['provenance']
    verify_binaries(provenance)
    binary = provenance['binaries']['candidate']['path']
    raw = Path('bench/phase-3-profile') / dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    raw.mkdir(parents=True)
    profile = json.loads(Path('bench/profile.json').read_text())
    cases = [dict(id='k23-n30', input='tests/fixtures/workload.psmcfa', arguments=['-p','4+5*3+4','-N','30','-t','15','-r','4','-I','0']),
             dict(id='k64-n5', input=profile['fixture']['file'], arguments=profile['arguments'])]
    results = []
    for case in cases:
        runs = []
        expected = None
        for backend in ['scalar','simd']:
            stats = raw / f"{case['id']}-{backend}.stats.json"
            output = raw / f"{case['id']}-{backend}.psmc"
            cmd = [binary,'--backend','cpu','--simd',('off' if backend=='scalar' else 'auto'),'--seed','42','--stats',str(stats),'-o',str(output),*case['arguments'],case['input']]
            result = subprocess.run(cmd,env=clean_env(),capture_output=True,text=True,check=True)
            (raw / f"{case['id']}-{backend}.stderr").write_text(result.stderr)
            data = output.read_bytes()
            if expected is not None: compare_output(expected,data)
            else: expected = data
            values = json.loads(stats.read_text())
            total = values['expectation_seconds'] + values['mstep_seconds']
            runs.append(dict(backend=backend,command=cmd,stats=values,output_sha256=digest(output),expectation_fraction_of_timed_sections=values['expectation_seconds']/total,mstep_fraction_of_timed_sections=values['mstep_seconds']/total))
        results.append(dict(**case,input_sha256=digest(Path(case['input'])),runs=runs,strict_output_match=True))
    verify_binaries(provenance)
    report = dict(status='passed',resource_policy=policy,created_utc=dt.datetime.now(dt.timezone.utc).isoformat(),provenance=provenance,raw_directory=str(raw),cases=results,limitations=['One diagnostic run per case and backend; use the repeated uninstrumented benchmark for speed claims.','E includes per-model preparation, sequence evaluation/cache and the aggregate normalizer; M includes Q0 and optimizer callbacks/model updates.','Other initialization, parsing, I/O, decoding and reporting costs are outside these sections.','No sampling-profiler attribution within the M-step is claimed.'],runner_sha256=digest(Path(__file__)))
    Path('bench/phase-3-profile.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status=report['status'],cases=[dict(id=c['id'],runs=[dict(backend=r['backend'],expectation_seconds=r['stats']['expectation_seconds'],mstep_seconds=r['stats']['mstep_seconds']) for r in c['runs']]) for c in results]),indent=2))

if __name__=='__main__':
    main()
