#!/usr/bin/env python3
"""Read-only consistency audit of the completed parallel milestone evidence."""
from pathlib import Path
import hashlib
import json
import re
import statistics

ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    checks = {}
    reports = {}
    for name in ('scaling', 'candidate', 'validation', 'candidate-build'):
        path = ROOT / f'bench/parallel-{name}.json'
        reports[name] = json.loads(path.read_text())
        assert reports[name]['status'] == 'passed', name
        checks[name + '_report_sha256'] = sha(path)
    checks['production_sha256'] = sha(ROOT / 'bin/psmc-rs')
    assert checks['production_sha256'] == 'b0fc39d7c31637221de1152fc0d502bb65c90d0a5b9d6672250fe3117f75bfa4'
    assert sha(ROOT / 'bench/parallel/baseline') == checks['production_sha256']
    for path, expected in reports['validation']['source_sha256'].items():
        assert sha(ROOT / path) == expected, path
    build = reports['candidate-build']
    changed = []
    for path, expected in build['source_sha256'].items():
        if sha(ROOT / path) != expected:
            changed.append(path)
            assert sha(ROOT / 'bench/parallel/candidate-build' / Path(path).name) == expected
    assert sorted(changed) == ['crates/psmc-cli/src/batch.rs', 'crates/psmc-cli/src/main.rs']
    assert sha(ROOT / 'bench/parallel/candidate') == build['candidate_sha256'] == reports['validation']['binary']['sha256']
    assert sha(ROOT / 'bench/parallel_candidate.py') == build['generator_sha256']
    counts = []
    for step in build['steps']:
        assert step['returncode'] == 0
        if 'test' in step['command']:
            counts.append(sum(map(int, re.findall(r'test result: ok\. (\d+) passed', step['output']))))
    assert counts == [33, 33]
    checks['candidate_unit_tests_per_profile'] = counts
    total = 0
    for name, expected_cases, expected_runs in [('scaling', 12, 4), ('candidate', 4, 18)]:
        report = reports[name]
        assert report['runner_sha256'] == sha(ROOT / 'bench/parallel_benchmark.py')
        assert len(report['cases']) == expected_cases
        for binary in report['binaries'].values():
            assert sha(ROOT / binary['path']) == binary['sha256']
        for case in report['cases']:
            assert len(case['runs']) == expected_runs
            for field in ('materialized_sha256', 'oracle_sha256'):
                for path, expected in case[field].items():
                    assert sha(ROOT / path) == expected, path
            for run in case['runs']:
                assert run['all_30_exact']
                assert (ROOT / run['output_directory']).is_dir()
                if run['label'] != 'vanilla':
                    assert run['actual_workers'] == case['workers']
                total += 30
            for label, summary in case['summary'].items():
                measured = [r for r in case['runs'] if r['label'] == label and not r['warmup']]
                for metric, values in summary.items():
                    raw = [r[metric] for r in measured]
                    assert values == dict(median=statistics.median(raw),minimum=min(raw),maximum=max(raw))
    assert total == 3600
    checks['timing_fit_comparisons'] = total
    validation = reports['validation']
    assert validation['runner_sha256'] == sha(ROOT / 'bench/parallel_validate.py')
    assert sha(ROOT / validation['oracle']['path']) == validation['oracle']['sha256']
    seeded = 0
    for check in validation['checks']:
        if 'comparisons' in check:
            assert check['all_draws_equal'] and len(check['comparisons']) == 30
            seeded += len(check['comparisons'])
        else:
            assert check['passed']
    assert seeded == 300
    checks['seeded_fit_comparisons'] = seeded
    checks['candidate_decision'] = 'rejected: slower median wall time in all four comparisons'
    for case in reports['candidate']['cases']:
        assert case['summary']['balanced']['wall_seconds']['median'] > case['summary']['baseline']['wall_seconds']['median']
    checks['production_source_unchanged'] = True
    checks['status'] = 'passed'
    (ROOT / 'bench/parallel-delivery-check.json').write_text(json.dumps(checks, indent=2) + '\n')
    print(json.dumps(checks, indent=2))

if __name__ == '__main__':
    main()
