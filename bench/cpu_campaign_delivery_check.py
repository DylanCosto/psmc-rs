#!/usr/bin/env python3
"""Cross-check the exact delivered source, binary, required gates and reports."""
import datetime as dt
import json
import os
from pathlib import Path
import re
from common import ROOT,save,sha256
from phase2_common import verify_binaries
from phase3_common import resource_policy


def main():
    os.chdir(ROOT);policy=resource_policy()
    names=['build','validation','scheduler','benchmark','review','cargo','assembly','extended','final-profile','gate-run']
    paths=['bench/cpu-campaign-'+n+'.json' for n in names]
    reports=dict(zip(names,[json.loads(Path(p).read_text()) for p in paths]))
    build=reports['build'];gate=reports['validation'];cargo=reports['cargo'];timing=reports['benchmark']
    actual=sha256('bin/psmc-rs')
    assert actual==build['rust_binary']['sha256']==gate['provenance']['binaries']['candidate']['sha256']==reports['scheduler']['provenance']['binaries']['candidate']['sha256']==timing['provenance']['binaries']['candidate']['sha256']==reports['review']['binary_sha256']==reports['assembly']['binary_sha256']==reports['extended']['provenance']['binaries']['candidate']['sha256']
    for report in [gate,reports['scheduler'],timing,reports['extended'],reports['final-profile']]:verify_binaries(report['provenance'])
    assert all(sha256(p)==h for p,h in build['source_sha256'].items())
    assert all(sha256(p)==h for p,h in cargo['source_sha256'].items())
    profile=reports['final-profile']
    assert all(build['source_sha256'].get(p)==h for p,h in profile['provenance']['source_sha256_at_freeze'].items())
    assert sha256(Path(profile['raw_directory'])/'bin/diagnostic')==profile['instrumented_binary_sha256']
    assert reports['build']['status']=='built'
    assert timing['status']=='passed_synthetic_timing_checks'
    assert all(r['status']=='passed' for n,r in reports.items() if n not in ['build','benchmark'])
    assert gate['complete_phase3a_selection']
    assert sum(r['passed'] for r in gate['backend_reports'].values())==340
    assert sum(len(r['comparisons']) for r in reports['scheduler']['runs'])==60
    assert all(r['workers']==1 and r['manifest']['contents']['workers']==1 for r in reports['scheduler']['runs'])
    assert len(reports['review']['checks'])==38
    tests=[sum(map(int,re.findall(r'test result: ok\. (\d+) passed;',s['output']))) for s in cargo['steps'] if s['command'][1]=='test']
    assert tests==[32,32],tests
    assert len(reports['extended']['cases'])==66 and reports['extended']['finite']==39
    assembly=reports['assembly'];assert assembly['fma_ops']==assembly['horizontal_ops']==0 and assembly['packed_avx_ops']>0
    old=json.loads(Path('bench/phase-3-build.json').read_text())['source_sha256']
    unchanged=[p for p in old if p.startswith('crates/psmc-core/src/')]+['crates/psmc-cpu/src/lib.rs','crates/psmc-cpu/src/engine.rs']
    assert all(sha256(p)==old[p] for p in unchanged)
    snaps=[s for r in gate['backend_reports'].values() for s in r['snapshots'].values()]
    assert len(snaps)==10 and sum(s['mismatches'] for s in snaps)==0
    retained={'bin/psmc-rs-phase3a':'8e417125208343026d56bae1b540b058371e4a0e949ca148a73c696b217f637b','bin/psmc-rs-phase2':'fd866573a007003d2388137270ec24f14acb436c42c7084ab8dac076fdabb59a','bin/psmc-rs-phase1':'e112ed9a8d7d98cc5e29f497e8567e1de96f3e0210a0cb324a79dc91c5e65dd0','../psmc-rust-phase-3-simd.zip':'ddb123cd6349803f399df9d18d1f47d2f25af6ee315e74a9170299e824e86c19','../psmc-rust-phase-2.zip':'b7291706a41ebf269402d99cabdee1eb2a75de1fafbbc25e347a7616905bf2bc','../psmc-rust-phase-1.zip':'5125a2e3c6bec8062f12fb5af15e3ac01da46b85d558dfbf3f35717025a22fc9'}
    assert all(sha256(p)==h for p,h in retained.items())
    missing=[]
    for p in [Path('README.md'),Path('PACKAGING.md'),*Path('docs').glob('cpu-campaign*.md')]:
        for target in re.findall(r'\]\(([^)]+)\)',p.read_text()):
            if '://' not in target and not target.startswith('#') and not (p.parent/target.split('#')[0]).exists():missing.append([str(p),target])
    assert not missing,missing
    report=dict(status='passed',created_utc=dt.datetime.now(dt.timezone.utc).isoformat(),resource_policy=policy,binary='bin/psmc-rs',sha256=actual,source_hashes_unchanged=True,unchanged_numerics={p:old[p] for p in unchanged},retained_release_sha256=retained,checks=dict(differential=340,extended=66,extended_finite=39,extended_pathologies=27,cli_review=38,scheduler_fits=60,unit_tests_each=32,snapshot_pairs=10,events=sum(s['events'] for s in snaps),finite_fields=sum(s['finite_numeric_values'] for s in snaps),snapshot_mismatches=0),evidence_sha256={p:sha256(p) for p in paths},runner_sha256=sha256(__file__))
    save('bench/cpu-campaign-delivery-check.json',report)
    print(json.dumps(dict(status=report['status'],binary_sha256=actual,checks=report['checks'])),flush=True)


if __name__=='__main__':main()
