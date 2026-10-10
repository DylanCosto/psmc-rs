#!/usr/bin/env python3
"""Verify the delivery is the exact SIMD build tested and measured."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import os
import re
from phase3_common import resource_policy

ROOT=Path(__file__).resolve().parents[1]
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    os.chdir(ROOT);policy=resource_policy()
    paths=['bench/phase-3-build.json','bench/phase-3-validation.json','bench/phase-3-scheduler.json','bench/phase-3-benchmark.json','bench/phase-3-review.json','bench/phase-3-cargo-checks.json','bench/phase-3-assembly.json','bench/phase-3-profile.json']
    build,gate,scheduler,timing,review,cargo,assembly,profile=[json.loads(Path(p).read_text()) for p in paths]
    actual=digest('bin/psmc-rs')
    assert actual==build['rust_binary']['sha256']==gate['provenance']['binaries']['candidate']['sha256']==scheduler['provenance']['binaries']['candidate']['sha256']==timing['provenance']['binaries']['candidate']['sha256']==review['binary_sha256']==assembly['binary_sha256']==profile['provenance']['binaries']['candidate']['sha256']
    assert all(digest(p)==h for p,h in build['source_sha256'].items())
    assert all(digest(p)==h for p,h in cargo['source_sha256'].items())
    assert digest('bin/psmc-rs-phase2')=='fd866573a007003d2388137270ec24f14acb436c42c7084ab8dac076fdabb59a'
    assert digest('bin/psmc-rs-phase1')=='e112ed9a8d7d98cc5e29f497e8567e1de96f3e0210a0cb324a79dc91c5e65dd0'
    assert all(d['status']=='passed' for d in [gate,scheduler,review,cargo,profile])
    assert timing['status']=='passed_synthetic_timing_checks'
    assert gate['complete_phase3a_selection']
    assert sum(r['passed'] for r in gate['backend_reports'].values())==340
    assert sum(len(r['comparisons']) for r in scheduler['runs'])==60
    assert all(r['workers']==1 and r['manifest']['contents']['workers']==1 for r in scheduler['runs'])
    assert len(review['checks'])==38
    tests=[sum(int(n) for n in re.findall(r'test result: ok\. (\d+) passed;',s['output'])) for s in cargo['steps'] if s['command'][1]=='test']
    assert tests==[32,32],tests
    assert assembly['fma_ops']==assembly['horizontal_ops']==0 and assembly['packed_avx_ops']>0
    old=json.loads(Path('bench/phase-2-build.json').read_text())['source_sha256']
    unchanged=['crates/psmc-core/src/'+f for f in ['hmm.rs','model.rs','model_workspace.rs','em.rs','optimizer.rs']]
    assert all(digest(p)==old[p] for p in unchanged)
    snaps=[v for r in gate['backend_reports'].values() for v in r['snapshots'].values()]
    assert len(snaps)==10 and sum(s['mismatches'] for s in snaps)==0
    missing=[]
    for p in [Path('README.md'),Path('PACKAGING.md'),*Path('docs').glob('phase-3*.md')]:
        for target in re.findall(r'\]\(([^)]+)\)',p.read_text()):
            if '://' not in target and not target.startswith('#') and not (p.parent/target.split('#')[0]).exists():missing.append([str(p),target])
    assert not missing,missing
    report=dict(status='passed',created_utc=dt.datetime.now(dt.timezone.utc).isoformat(),resource_policy=policy,binary='bin/psmc-rs',sha256=actual,source_hashes_unchanged=True,unchanged_phase2_numerics={p:old[p] for p in unchanged},checks=dict(differential=340,cli_review=38,scheduler_fits=60,unit_tests_each=32,snapshot_pairs=10,events=sum(s['events'] for s in snaps),finite_fields=sum(s['finite_numeric_values'] for s in snaps),snapshot_mismatches=0),evidence_sha256={p:digest(p) for p in paths},runner_sha256=digest(__file__))
    Path('bench/phase-3-delivery-check.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'binary_sha256':actual,'checks':report['checks']},indent=2))

if __name__=='__main__':main()
