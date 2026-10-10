#!/usr/bin/env python3
"""Check that delivered artifacts refer to one tested and measured binary."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import os
import re

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    os.chdir(ROOT)
    names = ['bench/phase-2-build.json','bench/phase-2-validation.json','bench/phase-2-scheduler.json',
             'bench/phase-2-benchmark.json','bench/phase-2-benchmark-audit.json','bench/phase2-review.json',
             'bench/phase-2-cargo-checks.json','bench/phase-2-harness-selftest.json']
    build,validation,scheduler,timing,audit,review,cargo,harness = [json.loads(Path(p).read_text()) for p in names]
    actual = digest(Path('bin/psmc-rs'))
    assert actual == build['rust_binary']['sha256'] == validation['provenance']['binaries']['candidate']['sha256'] == scheduler['provenance']['binaries']['candidate']['sha256'] == timing['provenance']['binaries']['candidate']['sha256'] == review['executable_sha256']
    assert all(digest(Path(p)) == expected for p,expected in build['source_sha256'].items())
    assert all(digest(Path(p)) == expected for p,expected in cargo['source_sha256'].items())
    assert digest(Path('bin/psmc-rs-phase1')) == 'e112ed9a8d7d98cc5e29f497e8567e1de96f3e0210a0cb324a79dc91c5e65dd0'
    assert all(x['status'] == 'passed' for x in [validation,scheduler,audit,cargo])
    assert timing['status'] == 'passed_synthetic_timing_checks' and not timing['failures']
    assert review['passed'] and harness['passed']
    assert sum(x['passed'] for x in validation['backend_reports'].values()) == 226
    assert sum(len(x['comparisons']) for x in scheduler['runs']) == 180
    assert len(review['checks']) == 17 and len(harness['tests']) == 9
    missing = []
    for file in [Path('README.md'),Path('PACKAGING.md'),*Path('docs').glob('phase-2*.md')]:
        for target in re.findall(r'\]\(([^)]+)\)',file.read_text()):
            if '://' in target or target.startswith('#'):
                continue
            if not (file.parent/target.split('#')[0]).exists():
                missing.append([str(file),target])
    assert not missing, missing
    report = dict(created_utc=dt.datetime.now(dt.timezone.utc).isoformat(),status='passed',
                  scope='Delivered binary matches build, differential, scheduler, review and timed frozen executables; production source matches final build/test hashes; new documentation links resolve.',
                  binary='bin/psmc-rs',sha256=actual,checks=dict(differential_controls=226,scheduler_fits=180,
                  cli_review_controls=17,harness_regression_tests=9,debug_release_unit_tests_each=27,
                  source_hashes_unchanged=True,historical_phase1_binary_unchanged=True,local_document_links_resolve=True),
                  evidence_sha256={p:digest(Path(p)) for p in names},runner_sha256=digest(Path(__file__)))
    Path('bench/phase-2-delivery-check.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status=report['status'],binary_sha256=actual,checks=report['checks']),indent=2))

if __name__ == '__main__':
    main()
