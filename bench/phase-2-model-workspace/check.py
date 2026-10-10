#!/usr/bin/env python3
"""Isolated exact comparisons and allocation witness; optional serial microtiming.

Run check.py for verification, or check.py --benchmark during an otherwise idle
measurement window. Timings use the default allocator; only the allocation probe
is compiled with a counting allocator. No shared Cargo target is touched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[2]
DEST = Path('bench/phase-2-model-workspace')
BUILD = Path('work/phase2-model-workspace')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(argv: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(argv, cwd=ROOT, check=True, capture_output=True,
                          env={**os.environ, 'LC_ALL': 'C'})


def compare(a: bytes, b: bytes) -> dict:
    if len(a) != len(b) or len(a) % 8:
        return {'passed': False, 'lengths': [len(a), len(b)]}
    finite = nans = infinities = mismatches = 0
    for i, ((x,), (y,)) in enumerate(zip(struct.iter_unpack('=d', a),
                                       struct.iter_unpack('=d', b))):
        if math.isnan(x) and math.isnan(y):
            nans += 1
        elif math.isinf(x) and x == y:
            infinities += 1
        elif math.isfinite(x) and math.isfinite(y):
            finite += 1
        # Compare signed zero exactly. Only paired NaNs may differ in payload.
        if not (math.isnan(x) and math.isnan(y)) and a[8*i:8*i+8] != b[8*i:8*i+8]:
            mismatches += 1
    return {'passed': mismatches == 0, 'byte_exact': a == b,
            'values': len(a)//8, 'finite_pairs': finite, 'nan_pairs': nans,
            'infinity_pairs': infinities, 'mismatches': mismatches}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmark', action='store_true')
    parser.add_argument('--cpu', type=int, help='pin this process and its children for measurement')
    parser.add_argument('--iterations', type=int, default=50000)
    parser.add_argument('--repetitions', type=int, default=7)
    args = parser.parse_args()
    if args.cpu is not None:
        os.sched_setaffinity(0, {args.cpu})
    affinity = sorted(os.sched_getaffinity(0))
    os.chdir(ROOT)
    BUILD.mkdir(exist_ok=True, parents=True)
    rustc = run(['rustc', '--version', '--verbose']).stdout.decode().strip()
    assert rustc.startswith('rustc 1.90.0 '), rustc
    commands = []
    diagnostics = {}
    binaries = {}
    for name, extra in [('check', []), ('allocations', ['--cfg', 'allocation_probe']),
                        ('tests', ['--test'])]:
        output = BUILD / name
        cmd = ['rustc', '--edition=2024', '-C', 'opt-level=2', '-C', 'codegen-units=1',
               *extra, str(DEST/'check.rs'), '-o', str(output)]
        result = run(cmd)
        commands.append(cmd)
        diagnostics[name] = result.stderr.decode()
        binaries[name] = str(output)
    outputs = {}
    for backend in ['dense', 'workspace']:
        cmd = [binaries['check'], backend]
        outputs[backend] = run(cmd).stdout
        (BUILD/f'{backend}.bin').write_bytes(outputs[backend])
        commands.append(cmd)
    legacy_report = json.loads(Path('bench/phase-1-isolated/results.json').read_text())
    c_path = Path('bench/phase-1-isolated/raw/model-c.bin')
    assert digest(c_path) == legacy_report['raw_output_sha256'][str(c_path)]
    dense_path = Path('crates/psmc-core/src/model.rs')
    assert digest(dense_path) == legacy_report['source_sha256'][str(dense_path)], \
        'Independent dense oracle changed since the Phase 1 C comparison.'
    comparisons = {
        'dense_vs_workspace': compare(outputs['dense'], outputs['workspace']),
        'retained_pinned_c_vs_workspace': compare(c_path.read_bytes(), outputs['workspace']),
    }
    allocation_cmd = [binaries['allocations'], 'allocations']
    allocation_text = run(allocation_cmd).stdout.decode().strip()
    commands.append(allocation_cmd)
    allocation_counts = {k: int(v) for k, v in
                         (item.split('=') for item in allocation_text.split())}
    unit_cmd = [binaries['tests']]
    unit_result = run(unit_cmd).stdout.decode()
    commands.append(unit_cmd)
    timing = {'status': 'not_run'}
    if args.benchmark:
        assert args.iterations > 0 and args.repetitions > 0
        timing = {'status': 'completed', 'scope': 'model update only; not full inference',
                  'iterations_per_sample': args.iterations,
                  'repetitions': args.repetitions,
                  'allocator': 'default system allocator; no allocation counter',
                  'cases': []}
        for n in [4, 23, 64]:
            raw = {'dense': [], 'workspace': []}
            for rep in range(args.repetitions):
                for backend in (['dense', 'workspace'] if rep % 2 == 0 else ['workspace', 'dense']):
                    cmd = [binaries['check'], 'benchmark', backend, str(n), str(args.iterations)]
                    raw[backend].append(float(run(cmd).stdout))
                    commands.append(cmd)
            medians = {name: statistics.median(values) for name, values in raw.items()}
            timing['cases'].append({'states': n, 'seconds': raw, 'median_seconds': medians,
                                    'dense_over_workspace': medians['dense']/medians['workspace']})
    source_paths = [Path(__file__).relative_to(ROOT), DEST/'check.rs', dense_path,
                    Path('crates/psmc-core/src/model_workspace.rs'),
                    Path('crates/psmc-core/src/math.rs'), Path('crates/psmc-core/src/rng.rs')]
    report = {
        'passed': all(c['passed'] for c in comparisons.values()),
        'scope': 'Phase 2 scratch lifetime change; arithmetic and loop order are unchanged',
        'reference_source_commit': legacy_report['source_commit'],
        'rustc': rustc, 'machine': platform.machine(), 'cpu_affinity': affinity,
        'cases': 60, 'comparisons': comparisons,
        'allocation_probe': allocation_counts,
        'unit_tests': {'passed': True, 'output': unit_result,
                       'repeated_candidate_cases': 360},
        'timing': timing,
        'source_sha256': {str(p): digest(p) for p in source_paths},
        'binary_sha256': {name: digest(Path(p)) for name, p in binaries.items()},
        'reference_evidence_sha256': digest(Path('bench/phase-1-isolated/results.json')),
        'retained_c_output_sha256': digest(c_path),
        'output_sha256': {name: hashlib.sha256(data).hexdigest() for name, data in outputs.items()},
        'commands': commands, 'compiler_diagnostics': diagnostics,
        'limitations': ['Synthetic model fixtures only.', 'No full inference/scheduling gate in this check.',
                       'No performance claim from allocation counts alone.',
                       'No CUDA or cross-platform gate.'],
    }
    (DEST/'results.json').write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    print(json.dumps({'passed': report['passed'], 'comparisons': comparisons,
                      'allocation_probe': allocation_counts, 'timing': timing,
                      'report': str(DEST/'results.json')}, indent=2))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
