"""Final read-only evidence audit, excluding installation and Git commit."""
import json
import os
import subprocess
from pathlib import Path
from common import ROOT, save, sha256, read_fasta, draw_bootstrap
from phase1_differential import compare_output

os.chdir(ROOT)
def read(name):
    return json.loads(Path(name).read_text())

reports = {str(p): read(p) for p in sorted(Path('bench').glob('exhaust-*.json'))
           if p.name != 'exhaust-audit.json'}
allowed = {'passed', 'passed_exactness', 'screened', 'built', 'measured', 'installed', None}
for path, report in reports.items():
    assert report.get('status') in allowed, (path, report.get('status'))
required = ['final-build', 'acceptance', 'full-validation', 'validation', 'cuda-control',
            'gpu-lanes', 'hybrid-combo', 'resident128', 'resident128-cpu']
assert all('bench/exhaust-' + name + '.json' in reports for name in required)
build = reports['bench/exhaust-final-build.json']
for group in ['source_sha256', 'configuration_sha256']:
    for path, digest in build[group].items():
        assert sha256(path) == digest, path
for entry in build['binaries'].values():
    assert sha256(entry['path']) == entry['sha256']
for step in build['steps']:
    assert step['returncode'] == 0 and sha256(step['log']) == step['sha256']
assert build['assembly']['fma'] == build['assembly']['horizontal'] == 0
# The CUDA driver/kernel and numerical oracle are unchanged in production.
unchanged = subprocess.check_output(['git', 'diff', '709831a', '--',
    'crates/psmc-cuda/src', 'crates/psmc-core/src', 'crates/psmc-cli/src/batch.rs'])
assert not unchanged
acceptance = reports['bench/exhaust-acceptance.json']
assert acceptance['performance_gate'] and acceptance['faster_pairs'] >= 2
assert acceptance['binaries']['candidate']['sha256'] == build['binaries']['cpu']['sha256']
regression = reports['bench/exhaust-full-validation.json']
assert regression['status'] == 'passed' and not regression['failures']
checks = snapshots = 0
for backend, entry in regression['backend_reports'].items():
    assert sha256(entry['report']) == entry['report_sha256']
    assert entry['failed'] == 0 and entry['full_bootstrap_finite'] == 27
    assert entry['full_bootstrap_pathologies'] == [16, 26, 28]
    checks += entry['passed']
    snapshots += len(entry['snapshots'])
extended = reports['bench/exhaust-validation.json']
assert extended['status'] == 'passed' and len(extended['extended']) == 66
assert extended['binary_sha256'] == build['binaries']['cpu']['sha256']
for row in extended['extended']:
    assert sha256(row['oracle']) == row['oracle_sha256']
    compare_output(Path(row['oracle']).read_bytes(), Path(row['output']).read_bytes())
for row in extended['human']:
    assert sha256(row['oracle']) == row['oracle_sha256']
    assert sha256(row['output']) == row['output_sha256']
    compare_output(Path(row['oracle']).read_bytes(), Path(row['output']).read_bytes())
cuda = reports['bench/exhaust-cuda-control.json']
assert cuda['status'] == 'passed' and len(cuda['cases']) == 2
assert cuda['binary_sha256'] == build['binaries']['cuda']['sha256']
for row in cuda['cases']:
    assert sha256(row['output']) == row['output_sha256']
    compare_output(Path(row['oracle']).read_bytes(), Path(row['output']).read_bytes())

screen_counts = {}
for name in ['cpu', 'more', 'refine', 'fusion', 'unroll', 'cuda']:
    screen = reports['bench/exhaust-' + name + '.json']
    cases = screen['cases'] if 'cases' in screen else [screen['case']]
    cases = {row['id']: row for row in cases}
    for row in cases.values():
        assert sha256(row['input']) == row['input_sha256']
        assert sha256(row['oracle']) == row['oracle_sha256']
    for entry in screen['variants'].values():
        binary = Path(entry['binary'])
        if str(binary) == 'bin/psmc-rs-cuda' and sha256(binary) != entry['sha256']:
            binary = Path('bin/psmc-rs-cuda-v0.4.0')
        assert sha256(binary) == entry['sha256']
        for path, digest in entry.get('source', {}).items():
            assert sha256(binary.parents[2] / path) == digest
    for row in screen['runs']:
        case = cases[row.get('case', next(iter(cases)))]
        assert sha256(row['output']) == row['output_sha256']
        compare_output(Path(case['oracle']).read_bytes(), Path(row['output']).read_bytes())
    screen_counts[name] = len(screen['runs'])

# Recheck every full HG batch, including rejected experiments and warmups.
data = read('bench/hg-input.json')
canonical = read('bench/hg-benchmark.json')['canonical_outputs']
records = read_fasta(data['blocks'])
expected = []
for row in canonical:
    assert sha256(row['path']) == row['sha256']
    expected.append(Path(row['path']).read_bytes())
batches = []
for path in sorted(Path('work/exhaust').rglob('manifest.json')):
    manifest = read(path)
    if manifest.get('seed') != data['seed'] or manifest.get('input') != data['blocks']:
        continue
    assert len(manifest['replicates']) == 30
    assert manifest['failed_replicates'] == manifest['nonfinite_replicates'] == 0
    outputs = []
    for i, row in enumerate(manifest['replicates']):
        output = path.parent / row['output']
        compare_output(expected[i], output.read_bytes())
        selected, draws = draw_bootstrap(records, data['seed'] + i)
        assert row['source_indices'] == selected
        actual = [json.loads(line) for line in (path.parent / row['draws']).read_text().splitlines()]
        assert actual[:-1] == [dict(event='bootstrap_draw', draw=j, **d) for j, d in enumerate(draws)]
        outputs.append(dict(path=str(output), sha256=sha256(output)))
    batches.append(dict(manifest=str(path), sha256=sha256(path), outputs=outputs))

# Preserve the exact first generator as well as its later optional K64 extension.
assert sha256('bench/exhaust_more_v1.py') == reports['bench/exhaust-more.json']['runner_sha256']
runner_hashes = {str(p): sha256(p) for p in sorted(Path('bench').glob('exhaust_*')) if p.is_file()}
report = dict(status='passed', runner_sha256=sha256(__file__),
    baseline_commit='709831a', reports={p: dict(status=r.get('status'), sha256=sha256(p))
                                      for p, r in reports.items()},
    source_sha256=build['source_sha256'], configuration_sha256=build['configuration_sha256'],
    binaries=build['binaries'], runner_hashes=runner_hashes,
    regression_checks=checks, ordered_traces=snapshots, extended_fixtures=66,
    screen_outputs_rechecked=screen_counts,
    human_batches=len(batches), human_batch_outputs=30*len(batches), batches=batches,
    exactness='All non-version output bytes; finite binary64 bits and signed zero in traces; reference nonfinite classes retained.',
    limitation='Available public chromosomes and synthetic probes only; shared host; no ARM/AVX-512/datacenter GPU or whole-genome claim.')
save('bench/exhaust-audit.json', report)
print({k: report[k] for k in ['status', 'regression_checks', 'ordered_traces', 'extended_fixtures', 'human_batches', 'human_batch_outputs']})
