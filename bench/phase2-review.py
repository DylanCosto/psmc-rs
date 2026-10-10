#!/usr/bin/env python3
"""Small independent Phase 2 CLI/scheduler review controls (no timing claims)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', default='target/release/psmc-rs')
    parser.add_argument('--report', default='bench/phase2-review.json')
    args = parser.parse_args()
    os.chdir(ROOT)
    binary = Path(args.binary).resolve()
    stage = Path(tempfile.mkdtemp(prefix='phase2-review-', dir=ROOT/'work'))
    immutable = stage/'psmc-rs'
    shutil.copy2(binary, immutable)
    digest = hashlib.sha256(immutable.read_bytes()).hexdigest()
    environment = {k: v for k, v in os.environ.items()
                   if k not in ('PSMC_SEED', 'PSMC_SNAPSHOT', 'PSMC_BOOTSTRAP_TRACE')}
    environment['LC_ALL'] = 'C'
    commands = []
    checks = []

    def run(arguments, env=None):
        result = subprocess.run([str(immutable), *map(str, arguments)],
                                capture_output=True, env=environment if env is None else env)
        commands.append({'arguments': [str(a).replace(str(ROOT), '${PROJECT}') for a in arguments],
                         'returncode': result.returncode,
                         'stderr': result.stderr.decode().replace(str(ROOT), '${PROJECT}')})
        return result

    def check(name, passed, evidence):
        checks.append({'name': name, 'passed': passed, 'evidence': evidence})

    missing = stage/'missing.psmcfa'
    missing.write_text('>missing\nNNNNNNNN\n')
    mixed = stage/'mixed.psmcfa'
    mixed.write_text('>missing\nNNNNNNNN\n>finite\nTTKTTTTT\n')
    good = stage/'good.psmcfa'
    good.write_text('>a\nTTKTTNTTTTKTTTTT\n>b\nTTKTTNTTTTKTTTTT\n>c\nTTKTT\n')

    output, snapshot = stage/'existing.psmc', stage/'existing.jsonl'
    output.write_text('KEEP OUTPUT\n')
    snapshot.write_text('KEEP SNAPSHOT\n')
    result = run(['--backend', 'cpu', '-N', '0', '-o', output, '--snapshot', snapshot, missing])
    check('all_missing_preserves_existing_output_and_snapshot',
          result.returncode == 2 and output.read_text() == 'KEEP OUTPUT\n'
          and snapshot.read_text() == 'KEEP SNAPSHOT\n',
          {'returncode': result.returncode, 'output_after': output.read_text(),
           'snapshot_after': snapshot.read_text()})

    trace = stage/'existing-trace.jsonl'
    trace.write_text('KEEP TRACE\n')
    output.write_text('KEEP OUTPUT\n')
    snapshot.write_text('KEEP SNAPSHOT\n')
    trace_environment = {**environment, 'PSMC_BOOTSTRAP_TRACE': str(trace)}
    result = run(['--backend', 'cpu', '-N', '0', '-b', '--seed', '45',
                  '-o', output, '--snapshot', snapshot, mixed], env=trace_environment)
    check('all_missing_sample_preserves_trace_output_snapshot',
          result.returncode == 2 and output.read_text() == 'KEEP OUTPUT\n'
          and snapshot.read_text() == 'KEEP SNAPSHOT\n' and trace.read_text() == 'KEEP TRACE\n',
          {'returncode': result.returncode, 'output_after': output.read_text(),
           'snapshot_after': snapshot.read_text(), 'trace_after': trace.read_text()})

    hardlink = stage/'alias.stats'
    os.link(good, hardlink)
    before = good.read_bytes()
    result = run(['-N', '0', '--stats', hardlink, good])
    check('stats_hardlink_input_rejected', result.returncode == 2 and good.read_bytes() == before,
          {'returncode': result.returncode, 'input_preserved': good.read_bytes() == before})

    result = run(['-N', '0', '-o', output, '--stats', output, good])
    check('stats_legacy_output_alias_rejected', result.returncode == 2,
          {'returncode': result.returncode})

    batch_bad = stage/'all-missing-batch'
    result = run(['bootstrap', '-N', '0', '--output-dir', batch_bad, missing])
    check('all_missing_batch_rejected_before_directory_creation',
          result.returncode == 2 and not batch_bad.exists(),
          {'returncode': result.returncode, 'directory_exists': batch_bad.exists()})

    budget_bad = stage/'budget-batch'
    result = run(['bootstrap', '-N', '0', '--memory-mib', '1', '--output-dir', budget_bad, good])
    check('too_small_memory_budget_rejected_before_directory_creation',
          result.returncode == 2 and not budget_bad.exists(),
          {'returncode': result.returncode, 'directory_exists': budget_bad.exists()})

    result = run(['bootstrap', '-N', '0', '--output-dir', stage, good])
    check('existing_batch_directory_rejected', result.returncode == 2,
          {'returncode': result.returncode})

    manifests = []
    batch_outputs = []
    for order, workers in [('forward', 1), ('reverse', 3)]:
        destination = stage/f'batch-{order}'
        result = run(['bootstrap', '--backend', 'cpu', '-N', '0', '-I', '0.1', '--seed', '42',
                      '--replicates', '4', '--workers', str(workers), '--task-order', order,
                      '--output-dir', destination, good])
        manifest = json.loads((destination/'manifest.json').read_text())
        manifests.append(manifest)
        batch_outputs.append([(destination/f'replicate-{i:02}.psmc').read_bytes() for i in range(4)])
        check(f'batch_{order}_bounded_workers_and_ordered_manifest',
              result.returncode == 0 and 1 <= manifest['workers'] <= workers
              and [r['index'] for r in manifest['replicates']] == list(range(4))
              and [r['seed'] for r in manifest['replicates']] == list(range(42, 46)),
              {'returncode': result.returncode, 'workers': manifest['workers'],
               'indices': [r['index'] for r in manifest['replicates']],
               'seeds': [r['seed'] for r in manifest['replicates']]})
    check('worker_count_and_reverse_task_order_preserve_outputs', batch_outputs[0] == batch_outputs[1],
          {'replicates_compared': 4})
    independent = []
    for i in range(4):
        result = run(['--backend', 'cpu', '-N', '0', '-I', '0.1', '-b', '--seed', str(42+i), good])
        independent.append(result.returncode == 0 and result.stdout == batch_outputs[0][i])
    check('batch_rng_replay_matches_independent_bootstrap_and_random_initialization', all(independent),
          {'replicates_equal': independent})

    failure_dir = stage/'mixed-batch'
    result = run(['bootstrap', '--backend', 'cpu', '-N', '0', '--seed', '42', '--replicates', '8',
                  '--workers', '3', '--output-dir', failure_dir, mixed])
    manifest = json.loads((failure_dir/'manifest.json').read_text())
    failures = [r for r in manifest['replicates'] if 'error' in r]
    successes = [r for r in manifest['replicates'] if 'error' not in r]
    check('partial_failure_is_reported_and_remaining_jobs_complete',
          result.returncode == 2 and 0 < len(failures) < 8 and len(successes)+len(failures) == 8
          and manifest['failed_replicates'] == len(failures)
          and all((failure_dir/r['output']).exists() for r in successes),
          {'returncode': result.returncode, 'failed_replicates': len(failures),
           'successful_replicates': len(successes), 'recorded_failures': failures})

    for flag, value in [('--workers', '0'), ('--replicates', '0'), ('--task-order', 'random'),
                        ('--memory-mib', '18446744073709551615')]:
        destination = stage/f'invalid-{flag[2:]}'
        result = run(['bootstrap', '-N', '0', flag, value, '--output-dir', destination, good])
        check('reject_'+flag[2:], result.returncode == 2 and not destination.exists(),
              {'returncode': result.returncode, 'directory_exists': destination.exists()})

    destination = stage/'seed-overflow'
    result = run(['bootstrap', '-N', '0', '--seed', str(2**63-1), '--replicates', '2',
                  '--output-dir', destination, good])
    check('seed_range_overflow_rejected_before_directory_creation',
          result.returncode == 2 and not destination.exists(),
          {'returncode': result.returncode, 'directory_exists': destination.exists()})

    report = {'passed': all(c['passed'] for c in checks), 'checks': checks,
              'executable_sha256': digest,
              'scope': 'small independent CLI and scheduler controls; no performance claim',
              'source_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                               [Path('crates/psmc-cli/src/main.rs'), Path('crates/psmc-cli/src/batch.rs')]},
              'commands': commands, 'raw_directory': str(stage.relative_to(ROOT))}
    Path(args.report).write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    print(json.dumps({'passed': report['passed'], 'checks': len(checks),
                      'failed': [c['name'] for c in checks if not c['passed']],
                      'report': args.report}, indent=2))


if __name__ == '__main__':
    main()
