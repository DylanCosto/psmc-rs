#!/usr/bin/env python3
"""Independently audit completed HG001 speed evidence, without rerunning fits."""
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT/'work/hg001-speed'
PRIOR = ROOT/'work/hg001-genome'
CONFIGS = ['c-one', 'strict-one', 'equivalent-one', 'strict-full', 'equivalent-full']
FIT = ['-p', '4+25*2+4+6', '-N', '30', '-t', '15', '-r', '5', '-I', '0']
GIB = 1024**3


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(path, data):
    path.write_text(json.dumps(data, indent=2)+'\n')


def relative(value):
    if isinstance(value, dict): return {k: relative(v) for k, v in value.items()}
    if isinstance(value, list): return [relative(v) for v in value]
    if isinstance(value, str): return value.replace(str(ROOT)+'/', '')
    return value


def close(a, b):
    assert math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12), (a, b)


def numeric(text):
    return ''.join(line for line in text.splitlines(keepends=True)
                   if not line.startswith('MM\tVersion:'))


def parse_time(text):
    # Separate parser from the campaign's timing helpers.
    def field(label):
        return re.search(r'^\s*'+re.escape(label)+r':\s*(.+)$', text, re.M).group(1)
    duration = field('Elapsed (wall clock) time (h:mm:ss or m:ss)')
    parts = list(map(float, duration.split(':')))
    assert len(parts) in [2, 3]
    wall = sum(x*60**i for i, x in enumerate(reversed(parts)))
    timing = {'user_seconds': float(field('User time (seconds)')),
              'system_seconds': float(field('System time (seconds)')),
              'peak_rss_kib': float(field('Maximum resident set size (kbytes)'))}
    assert wall > 0 and int(field('Exit status')) == 0
    return wall, timing, int(field('Swaps')), field('Command being timed').strip('"')


def check_fit(text):
    lines = text.splitlines()
    assert [int(x.split()[1]) for x in lines if x.startswith('RD\t')] == list(range(31))
    for line in lines:
        if line.startswith(('PA\t', 'LK\t', 'TR\t', 'RS\t', 'QD\t', 'QU\t')):
            parts = line.split()
            values = parts[2:] if parts[0] == 'PA' else parts[1:]
            if parts[0] in ['QD', 'QU']:
                assert len(values) == 3 and values[1] == '->'
                values = [values[0], values[2]]
            for token in values:
                assert math.isfinite(float(token)), line
            if parts[0] == 'PA': assert all(float(v) > 0 for v in values)


def audit():
    report = read(RAW/'report.json'); manifest = read(RAW/'manifest.json')
    assert report['manifest'] == manifest
    assert manifest['diff_sha256'] == hashlib.sha256(b'').hexdigest()
    assert manifest['allowed_cpus'] == list(range(16)) and manifest['single_cpu'] == 0
    for name, digest in manifest['source_hashes'].items():
        assert sha(ROOT/name) == digest
        committed = subprocess.check_output(['git', 'show', f"{manifest['commit']}:{name}"], cwd=ROOT)
        assert hashlib.sha256(committed).hexdigest() == digest
    for name, digest in manifest['binaries'].items(): assert sha(PRIOR/'binaries'/name) == digest
    assert sha(PRIOR/'HG001_GRCh38_autosomes.psmcfa') == manifest['input_sha256']
    prior = read(PRIOR/'audit.json')
    assert report['prior_audit'] == prior
    assert prior['audit_passed'] and prior['strict_c_exact']
    assert prior['report_sha256'] == sha(PRIOR/'report.json')
    assert prior['input_sha256'] == manifest['input_sha256']
    references = {m: (PRIOR/f'{m}.out').read_text() for m in ['c', 'strict', 'equivalent']}
    for mode in references:
        assert sha(PRIOR/f'{mode}.out') == read(PRIOR/f'{mode}.done.json')['output_sha256']
        check_fit(references[mode])
    assert numeric(references['c']) == numeric(references['strict'])
    # The order is specified independently from the runner's schedule function.
    expected = [('warmup', c) for c in CONFIGS[:3]]
    for i, order in enumerate([CONFIGS[:3], [CONFIGS[1], CONFIGS[2], CONFIGS[0]],
                              [CONFIGS[2], CONFIGS[0], CONFIGS[1]]], 1):
        expected += [(f'repeat-{i}', c) for c in order]
    expected += [('warmup', c) for c in CONFIGS[3:]]
    for i, order in enumerate([CONFIGS[3:], CONFIGS[:2:-1], CONFIGS[3:]], 1):
        expected += [(f'repeat-{i}', c) for c in order]
    rows = report['rows']
    assert [(r['phase'], r['config']) for r in rows] == expected
    assert manifest['schedule'] == [list(v) for v in expected]
    assert read(RAW/'progress.json') == rows and len(rows) == 20
    samples = [json.loads(line) for line in (RAW/'resources.jsonl').read_text().splitlines()]
    assert all(a['time'] <= b['time'] for a, b in zip(samples, samples[1:]))
    assert not (RAW/'stop.json').exists()
    checks = []; end = 0
    for row in rows:
        name = row['phase']+'-'+row['config']; mode, size = row['config'].split('-')
        requested = 1 if size == 'one' else 16
        cmd = ['/usr/bin/taskset', '-c', '0' if size == 'one' else '0-15',
               str(PRIOR/'binaries'/('c' if mode == 'c' else 'rust'))]
        if mode != 'c':
            cmd += ['--mode', mode, '--record-workers', str(requested), '--stats', str(RAW/f'{name}.stats.json')]
            if mode == 'strict': cmd += ['--memory-mib', '8192']
        cmd += [*FIT, str(PRIOR/'HG001_GRCh38_autosomes.psmcfa')]
        done = read(RAW/f'{name}.done.json')
        assert done['command'] == cmd and row['command'] == relative(cmd)
        assert all(row[k] == relative(v) for k, v in done.items())
        assert done['exit_code'] == 0 and done['ceiling_gib'] == 10
        assert done['started'] >= end+5 if end else True
        end = done['started']+done['seconds']
        assert done['seconds'] < 6*3600
        attempts = list(RAW.glob(name+'.attempt-*.json'))
        assert len(attempts) == 1 and read(attempts[0]) == done
        assert not list(RAW.glob(name+'.partial-*'))
        text = (RAW/f'{name}.out').read_text(); check_fit(text)
        assert sha(RAW/f'{name}.out') == row['output_sha256']
        assert numeric(text) == numeric(references[mode]) and row['output_exact']
        if mode == 'strict': assert numeric(text) == numeric(references['c'])
        wall, timing, swaps, timed_command = parse_time((RAW/f'{name}.time').read_text())
        assert timed_command == ' '.join(cmd)
        close(wall, row['wall_seconds']); assert timing == row['timing']
        assert wall <= done['seconds'] < wall+3
        close((timing['user_seconds']+timing['system_seconds'])/wall, row['cpu_time_over_wall'])
        assert row['host'] == read(RAW/f'{name}.host.json')
        assert row['host']['before']['time'] <= done['started']
        assert row['host']['after']['time'] >= end
        stats = None if mode == 'c' else read(RAW/f'{name}.stats.json')
        assert stats == row['stats']
        workers = requested
        if stats:
            assert stats['mode'] == mode and stats['backend'] == 'cpu'
            assert stats['iterations'] == 30 and not stats['nonfinite_output']
            assert stats['sequence_visits'] == 660 and stats['sequence_evaluations'] == 660
            assert stats['simd_selected'] == 'avx' and stats['cuda_launches'] == 0
            original_stats = read(PRIOR/f'{mode}.stats.json')
            for field in ['model_updates', 'structured_fallbacks']:
                assert stats[field] == original_stats[field]
            if mode == 'strict':
                a = stats['memory_admission']; workers = a['workers']
                assert a['requested_workers'] == requested and a['budget_bytes'] == 8*GIB
                assert a['estimated_bytes'] <= a['budget_bytes']
                assert workers == (1 if size == 'one' else 2)
            else: assert stats['memory_admission'] is None
        assert row['workers'] == workers
        stage_samples = [s for s in samples if s['stage'] == name]
        assert stage_samples and all(done['started']-2 <= s['time'] <= end+2 for s in stage_samples)
        checks.append({'name': name, 'output_sha256': sha(RAW/f'{name}.out'),
                       'timing_sha256': sha(RAW/f'{name}.time'), 'stats_sha256': sha(RAW/f'{name}.stats.json') if stats else None,
                       'output_exact': True, 'swaps': swaps, 'resource_samples': len(stage_samples)})
    commit_time = int(subprocess.check_output(['git', 'show', '-s', '--format=%ct', manifest['commit']], cwd=ROOT))
    assert commit_time < rows[0]['started']
    summaries = {}
    for config in CONFIGS:
        group = [r for r in rows if r['config'] == config and r['phase'] != 'warmup']
        assert len(group) == 3
        walls = [r['wall_seconds'] for r in group]
        values = {'median_seconds': statistics.median(walls), 'range_seconds': [min(walls), max(walls)],
                  'peak_rss_mib': max(r['timing']['peak_rss_kib'] for r in group)/1024,
                  'actual_workers': sorted({r['workers'] for r in group})}
        for key, value in values.items(): assert report['summary'][config][key] == value
        values.update(wall_seconds=walls,
                      cpu_seconds=[r['timing']['user_seconds']+r['timing']['system_seconds'] for r in group],
                      mean_cpus=[r['cpu_time_over_wall'] for r in group])
        summaries[config] = values
    for config, s in summaries.items():
        s['speedup_vs_c_one'] = summaries['c-one']['median_seconds']/s['median_seconds']
        close(s['speedup_vs_c_one'], report['summary'][config]['speedup_vs_c_one'])
        if config.endswith('-full'):
            s['speedup_vs_same_mode_one'] = summaries[config.replace('-full', '-one')]['median_seconds']/s['median_seconds']
            close(s['speedup_vs_same_mode_one'], report['summary'][config]['speedup_vs_same_mode_one'])
    resources = {'sample_count': len(samples), 'min_available_ram_gib': min(s['available_ram'] for s in samples)/GIB,
                 'min_free_disk_gib': min(s['free_disk'] for s in samples)/GIB,
                 'max_campaign_mib': max(s['campaign_bytes'] for s in samples)/1024**2,
                 'max_sampled_group_rss_gib': max(s['rss_bytes'] for s in samples)/GIB,
                 'recorded_stop': False, 'swaps_all_fits': sum(x['swaps'] for x in checks)}
    assert resources['min_available_ram_gib'] >= 4 and resources['min_free_disk_gib'] >= 25
    assert resources['max_campaign_mib'] <= 4096
    result = {'audit_passed': True, 'report_sha256': sha(RAW/'report.json'),
              'resources_sha256': sha(RAW/'resources.jsonl'), 'protocol_commit': manifest['commit'],
              'fits_checked': 20, 'measured_fits': 15, 'excluded_warmups': 5,
              'all_outputs_exact_within_mode': True, 'strict_c_exact': True,
              'prior_equivalent_screen_passed': prior['equivalent_screen_passed'],
              'checks': checks, 'resources': resources, 'summary': summaries,
              'worker_evidence': 'Strict workers read from admission stats. Equivalent workers configured by CLI; no independent per-thread occupancy trace. CPU/wall recorded.'}
    save(RAW/'audit.json', result)
    save(ROOT/'bench/hg001-speed-audit.json', result)
    # Compact analysis evidence only: no raw input or CPU-info dump.
    compact = {**report, 'manifest': {k: v for k, v in manifest.items() if k != 'cpu_info'}}
    save(ROOT/'bench/hg001-speed-results.json', compact)
    return result


if __name__ == '__main__':
    result = audit()
    print(json.dumps({k: v for k, v in result.items() if k != 'checks'}, indent=2))
