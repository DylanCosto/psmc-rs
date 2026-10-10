#!/usr/bin/env python3
"""Run unchanged upstream conversion and plotting-data scripts on paired output."""
import json
import os
from pathlib import Path
import shutil
import subprocess

from common import ROOT, save, sha256, nonfinite_records
from phase1_differential import compare_output

RAW = ROOT / 'bench/raw/phase1-output-tools'
REPORT = ROOT / 'bench/phase1-output-tools.json'


def run(command, stem):
    with stem.with_suffix('.stdout').open('wb') as out, stem.with_suffix('.stderr').open('wb') as err:
        result = subprocess.run(command, cwd=ROOT, stdout=out, stderr=err, timeout=180,
                                env={k:v for k,v in os.environ.items() if not k.startswith('PSMC_')})
    return {'command': command, 'exit_code': result.returncode,
            'stdout': str(stem.with_suffix('.stdout').relative_to(ROOT)),
            'stdout_sha256': sha256(stem.with_suffix('.stdout')),
            'stderr': str(stem.with_suffix('.stderr').relative_to(ROOT)),
            'stderr_sha256': sha256(stem.with_suffix('.stderr'))}


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    report = {'source_commit': '82fa2ada83ee463fe1251b562ae3d60e82d7ad6a',
              'fixture': 'tests/fixtures/workload.psmcfa', 'iterations': 30,
              'plot_rendering': 'not_run' if shutil.which('gnuplot') is None else 'attempted',
              'plot_rendering_note': 'Data and parameter generation are checked independently of gnuplot rendering.',
              'upstream_scripts': {}, 'runs': {}, 'checks': {}}
    for name in ('psmc2history.pl', 'psmc_plot.pl'):
        path = ROOT / 'work/vanilla/utils' / name
        report['upstream_scripts'][name] = {'path': str(path.relative_to(ROOT)), 'sha256': sha256(path)}
    outputs = {}
    for name, binary in [('vanilla', 'work/vanilla/psmc'), ('rust', 'target/release/psmc-rs')]:
        stem = RAW / name
        command = [binary, '-p', '4+5*3+4', '-N', '30', '-t', '15', '-r', '4', '-I', '0', report['fixture']]
        fit = run(command, stem)
        assert fit['exit_code'] == 0, fit
        psmc = stem.with_suffix('.stdout')
        assert not nonfinite_records(psmc.read_text()), 'Finite conversion fixture failed'
        outputs[name] = psmc.read_bytes()
        history = run(['perl', 'work/vanilla/utils/psmc2history.pl', '-n', '30', str(psmc.relative_to(ROOT))], RAW / (name + '-history'))
        assert history['exit_code'] == 0 and (RAW / (name + '-history.stdout')).read_text().startswith('T ')
        prefix = 'bench/raw/phase1-output-tools/' + name + '-plot'
        plotting = run(['perl', 'work/vanilla/utils/psmc_plot.pl', '-R', '-n', '30', prefix, str(psmc.relative_to(ROOT))], RAW / (name + '-plot-script'))
        generated = {}
        for suffix in ('.0.txt', '.par'):
            path = ROOT / (prefix + suffix)
            assert path.exists() and path.stat().st_size > 0, f'Missing plot data: {path}'
            generated[suffix] = {'path': str(path.relative_to(ROOT)), 'sha256': sha256(path), 'bytes': path.stat().st_size}
        report['runs'][name] = {'binary_sha256': sha256(ROOT / binary), 'fit': fit,
                                'history': history, 'plot_script': plotting, 'plot_data': generated}
    report['checks']['legacy_output'] = compare_output(outputs['vanilla'], outputs['rust'])
    report['checks']['history_bytes_equal'] = (RAW/'vanilla-history.stdout').read_bytes() == (RAW/'rust-history.stdout').read_bytes()
    report['checks']['plot_data_bytes_equal'] = all((RAW/('vanilla-plot'+s)).read_bytes() == (RAW/('rust-plot'+s)).read_bytes() for s in ('.0.txt', '.par'))
    assert report['checks']['history_bytes_equal'] and report['checks']['plot_data_bytes_equal']
    report['passed'] = True
    save(REPORT, report)
    print(json.dumps({'passed': True, 'history_bytes_equal': True, 'plot_data_bytes_equal': True,
                      'plot_rendering': report['plot_rendering'], 'report': str(REPORT.relative_to(ROOT))}))

if __name__ == '__main__':
    main()
