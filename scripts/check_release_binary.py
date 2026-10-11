#!/usr/bin/env python3
"""Replay a fixed whole-genome pair using a verified extracted release executable."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'bench'))
import adoption_qualification as guard


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text())
def save(path, data): Path(path).write_text(json.dumps(data,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extracted-dir', required=True, type=Path)
    args=parser.parse_args();installed=args.extracted_dir.resolve()
    build=read(installed/'BUILD.json');binary=installed/'psmc-rs'
    assert build['version']=='0.8.0' and build['target']=='x86_64-unknown-linux-gnu'
    assert sha(binary)==build['binary_sha256']
    for line in (installed/'SHA256SUMS').read_text().splitlines():
        digest,name=line.split('  ',1);path=(installed/name).resolve()
        assert path.is_relative_to(installed) and sha(path)==digest
    campaign=ROOT/'work/adoption-qualification'
    assert read(campaign/'continuation.json')['status']=='completed'
    audit=read(ROOT/'bench/adoption-qualification-audit.json');assert audit['integrity_passed']
    output=ROOT/'work/release-binary-check';output.mkdir(exist_ok=False)
    guard.OUT=output  # Separate process/directory; frozen runner source and campaign are untouched.
    records={}
    try:
        for mode in ['strict','equivalent']:
            trace=output/(mode+'.draws.jsonl')
            os.environ['PSMC_BOOTSTRAP_TRACE']=str(trace)
            run=guard.stage(mode,[binary,'--mode',mode,'-b','--seed','20261011',
                '--record-workers','4','--memory-mib','2048','--stats',output/(mode+'.stats.json'),
                *guard.p.FIT,campaign/'blocks.psmcfa'])
            assert sha(output/(mode+'.out'))==sha(campaign/mode/'replicate-00.psmc'), 'same-mode output changed'
            assert sha(trace)==sha(campaign/mode/'replicate-00.draws.jsonl'), 'bootstrap draws changed'
            records[mode]=dict(run=run,output_exact=True,draws_exact=True,
                               trace_sha256=sha(trace),stats=read(output/(mode+'.stats.json')),
                               stats_sha256=sha(output/(mode+'.stats.json')),time_sha256=sha(output/(mode+'.time')))
        result=dict(status='passed',release_build=build,
                    checker_source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                    checker_sha256=sha(__file__),protocol_sha256=sha(ROOT/'docs/release-binary-check-protocol.md'),
                    input_sha256=sha(campaign/'blocks.psmcfa'),campaign_source_commit=read(campaign/'frozen.json')['commit'],
                    cases=records,resources_sha256=sha(output/'resources.jsonl'),
                    scope='Same-mode final binary continuity, not a speed benchmark')
        def relative(x):
            if isinstance(x,str):return x.replace(str(ROOT)+'/', '')
            if isinstance(x,list):return [relative(v) for v in x]
            if isinstance(x,dict):return {k:relative(v) for k,v in x.items()}
            return x
        save(ROOT/'bench/release-binary-check.json',relative(result))
        print('Both released-binary whole-genome bootstrap outputs and draw traces match frozen fits exactly')
    except BaseException as error:
        save(output/'failure.json',dict(error=repr(error)));raise
    finally:os.environ.pop('PSMC_BOOTSTRAP_TRACE',None)


if __name__=='__main__':main()
