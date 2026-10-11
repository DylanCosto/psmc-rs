#!/usr/bin/env python3
"""Release compatibility checks against a retained pre-transition executable."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def numerical(data):
    return b''.join(x for x in data.splitlines(keepends=True) if not x.startswith(b'MM\tVersion:'))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary', type=Path, required=True)
    p.add_argument('--previous', type=Path, default=ROOT/'bin/psmc-rs-v0.6.3')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); root = a.output.resolve(); root.mkdir(parents=True, exist_ok=False)
    binary = a.binary.resolve(); previous = a.previous.resolve()
    fixture = ROOT/'tests/fixtures/workload.psmcfa'
    common = ['-p', '1+2', '-N', '3', '-t', '15', '-r', '4', '-I', '0', '--seed', '42']
    checks = []; commands = []
    environment = dict(os.environ); environment.pop('PSMC_SNAPSHOT', None); environment.pop('PSMC_SEED', None)

    def execute(name, cmd, stdin=None, env=None):
        result = subprocess.run(list(map(str, cmd)), input=stdin, capture_output=True,
                                cwd=root, env=env or environment, timeout=180)
        (root/f'{name}.out').write_bytes(result.stdout); (root/f'{name}.stderr').write_bytes(result.stderr)
        commands.append({'name': name, 'command': [str(x).replace(str(ROOT)+'/', '') for x in cmd],
                         'exit_code': result.returncode, 'stdout_sha256': sha(root/f'{name}.out')})
        assert result.returncode == 0, (name, result.stderr.decode())
        return result.stdout

    reference = {}
    cases = {'fit': [], 'segments': ['-d'], 'posterior': ['-D'], 'scales': ['-s'],
             'capped': ['-d', '-C', '1'], 'divergence': ['-T', '0.1'],
             'randomized': ['-I', '0.2']}
    for mode in ['strict', 'equivalent']:
        for name, extra in cases.items():
            old = execute(f'old-{mode}-{name}', [previous, '--mode', mode, '--record-workers', '1', *common, *extra, fixture])
            new = execute(f'new-{mode}-{name}', [binary, '--mode', mode, '--record-workers', '2', '--memory-mib', '256', *common, *extra, fixture])
            assert numerical(old) == numerical(new), (mode, name)
            checks.append(f'{mode}: prior-version parity {name}')
            if name == 'fit': reference[mode] = new
    implicit = execute('implicit', [binary, *common, fixture])
    assert numerical(implicit) == numerical(reference['equivalent']); checks.append('implicit CPU equivalent')
    compressed = root/'input.psmcfa.gz'
    with gzip.open(compressed, 'wb') as stream: stream.write(fixture.read_bytes())
    for name, inp, data in [('gzip', compressed, None), ('stdin', '-', fixture.read_bytes())]:
        actual = execute(name, [binary, *common, inp], stdin=data)
        assert numerical(actual) == numerical(implicit); checks.append(name)
    # Parameter initialization uses the same saved equivalent parameters in both versions.
    params = root/'params.txt'
    params.write_bytes([l[3:] for l in reference['equivalent'].splitlines() if l.startswith(b'PA\t')][-1]+b'\n')
    for mode in ['strict', 'equivalent']:
        old = execute(f'old-initial-{mode}', [previous, '--mode', mode, *common, '-i', params, fixture])
        new = execute(f'new-initial-{mode}', [binary, '--mode', mode, *common, '-i', params, fixture])
        assert numerical(old) == numerical(new); checks.append(f'{mode}: initialized parameters')
    for mode in ['strict', 'equivalent']:
        dirs = []
        for label, exe in [('old', previous), ('new', binary)]:
            directory = root/f'{label}-batch-{mode}'; dirs.append(directory)
            # Omit mode for the new equivalent batch to verify the actual default.
            select = [] if label == 'new' and mode == 'equivalent' else ['--mode', mode]
            execute(f'{label}-batch-{mode}', [exe, 'bootstrap', *select, '--workers', '2', '--replicates', '3',
                    '--memory-mib', '256', '--output-dir', directory, *common, fixture])
        files = sorted(dirs[0].glob('*.psmc')); assert len(files) == 3
        for path in files:
            assert numerical(path.read_bytes()) == numerical((dirs[1]/path.name).read_bytes())
        for path in dirs[0].glob('*.draws.jsonl'):
            assert path.read_bytes() == (dirs[1]/path.name).read_bytes()
        for directory in dirs:
            manifest = json.loads((directory/'manifest.json').read_text())
            assert manifest['mode'] == mode and manifest['failed_replicates'] == 0
            assert manifest['workers'] <= 2 and manifest['memory_mib'] == 256
        checks.append(f'{mode}: deterministic bootstrap outputs/draws/admission')
    # QU -> QD is deliberately only a parser-compatibility control: these tools
    # must ignore either diagnostic, not treat their values as interchangeable.
    utility_input = root/'utility.psmc'; utility_input.write_bytes(implicit)
    renamed = root/'renamed-diagnostic.psmc'; renamed.write_bytes(implicit.replace(b'\nQU\t', b'\nQD\t'))
    utilities = ROOT/'work/vanilla/utils'
    for tool in ['psmc2history.pl', 'avg.pl', 'psmc_trunc.pl']:
        aout = execute(tool, ['perl', utilities/tool, '-n', '3', utility_input])
        bout = execute('control-'+tool, ['perl', utilities/tool, '-n', '3', renamed])
        assert aout, tool
        if tool == 'psmc_trunc.pl':
            assert b'\nQU\t' in aout and aout.replace(b'\nQU\t', b'\nQD\t') == bout
            checks.append(f'{tool}: preserves QU verbatim; other converted records unchanged')
        else:
            assert aout == bout, tool
            checks.append(f'{tool}: ignores objective diagnostic')
    # Capture gnuplot stdin without claiming to render an unavailable renderer.
    stub = root/'capture-bin'; stub.mkdir()
    (stub/'gnuplot').write_text('#!/bin/sh\ncat > "$PSMC_CAPTURE"\n')
    (stub/'gnuplot').chmod(0o755)
    plotting_env = {**environment, 'PATH': str(stub)+':'+environment['PATH'], 'PSMC_CAPTURE': str(root/'gnuplot-input.txt')}
    prefix = root/'plot'
    execute('plot', ['perl', utilities/'psmc_plot.pl', '-R', '-n', '3', '-m', '0', prefix, utility_input], env=plotting_env)
    original = {f.name: f.read_bytes() for f in root.glob('plot.*')}; assert (root/'plot.0.txt').exists()
    execute('plot-control', ['perl', utilities/'psmc_plot.pl', '-R', '-n', '3', '-m', '0', prefix, renamed], env=plotting_env)
    assert original == {f.name: f.read_bytes() for f in root.glob('plot.*')}
    assert b'plot ' in (root/'gnuplot-input.txt').read_bytes()
    checks.append('psmc_plot: data and gnuplot input ignore objective diagnostic')
    report = {'binary_sha256': sha(binary), 'previous_sha256': sha(previous), 'checks': checks,
              'commands': commands, 'passed': True, 'plot_rendering': 'not_run; gnuplot input captured only',
              'utility_hashes': {t: sha(utilities/t) for t in ['psmc2history.pl', 'avg.pl', 'psmc_trunc.pl', 'psmc_plot.pl']}}
    (root/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'passed': True, 'checks': len(checks), 'plot_rendering': report['plot_rendering']}))


if __name__ == '__main__': main()
