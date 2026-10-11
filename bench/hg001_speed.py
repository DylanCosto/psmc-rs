#!/usr/bin/env python3
"""Queue a bounded, repeated speed comparison behind the HG001 integrity audit."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import statistics
import subprocess
import time

import hg001_genome_run as base

CONFIGS = ['c-one', 'strict-one', 'equivalent-one', 'strict-full', 'equivalent-full']
SOURCES = [*base.SOURCES, 'bench/hg001_speed.py', 'docs/hg001-speed-protocol.md']


def schedule():
    jobs = []
    for configs, orders in [
        (CONFIGS[:3], [CONFIGS[:3], CONFIGS[1:3]+CONFIGS[:1], [CONFIGS[2], *CONFIGS[:2]]]),
        (CONFIGS[3:], [CONFIGS[3:], CONFIGS[3:][::-1], CONFIGS[3:]])]:
        jobs.extend(('warmup', c) for c in configs)
        for i, order in enumerate(orders, 1):
            jobs.extend((f'repeat-{i}', c) for c in order)
    return jobs


def cpu_list(text):
    result = set()
    for part in text.strip().split(','):
        ends = list(map(int, part.split('-')))
        result.update(range(ends[0], ends[-1]+1))
    return result


def command(source, root, name, config):
    mode, size = config.split('-')
    cmd = ['/usr/bin/taskset', '-c', '0' if size == 'one' else '0-15',
           str(source/'binaries'/('c' if mode == 'c' else 'rust'))]
    if mode != 'c':
        cmd += ['--mode', mode, '--record-workers', '1' if size == 'one' else '16',
                '--stats', str(root/f'{name}.stats.json')]
        if mode == 'strict':
            cmd += ['--memory-mib', '8192']
    return [*cmd, *base.p.FIT, str(source/'HG001_GRCh38_autosomes.psmcfa')]


def wall_seconds(text):
    line = next(x for x in text.splitlines() if 'Elapsed (wall clock) time' in x)
    parts = line.split('): ', 1)[1].strip().split(':')
    result = 0.
    for part in parts:
        result = result*60+float(part)
    assert result > 0
    return result


def host_sample():
    return {'time': time.time(), 'load_average': list(os.getloadavg()),
            'cpu_pressure': Path('/proc/pressure/cpu').read_text(),
            'cpu_ticks': Path('/proc/stat').read_text().splitlines()[0]}


def dependency_live(source):
    # Both processes must finish before timing; do not mistake a lock file for life.
    for path in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            args = path.read_bytes().split(b'\0')
            if any(Path(os.fsdecode(a)).name in ('hg001_genome_run.py', 'hg001_genome_finish.py') for a in args):
                if str(source).encode() in args or b'work/hg001-genome' in args:
                    return True
        except (OSError, ValueError):
            pass
    return False


def dependency_ready(source):
    if (source/'stop.json').exists():
        raise RuntimeError('preceding comparison stopped; preserve evidence and investigate')
    if dependency_live(source):
        return False
    if not (source/'audit.json').exists():
        raise RuntimeError('preceding comparison has no live owner and no completed audit')
    audit = json.loads((source/'audit.json').read_text())
    assert audit['audit_passed'] and audit['strict_c_exact'], 'preceding integrity/strict gate failed'
    assert audit['report_sha256'] == base.sha(source/'report.json')
    return True


def verify_output(text, expected):
    base.p.curve(text)  # Checks all 31 rounds and finite, positive final parameters.
    assert base.p.numerical(text) == base.p.numerical(expected), 'numerical output changed'


def summarize(rows):
    summary = {}
    for config in CONFIGS:
        values = [r for r in rows if r['config'] == config and r['phase'] != 'warmup']
        assert len(values) == 3
        walls = [r['wall_seconds'] for r in values]
        summary[config] = {'median_seconds': statistics.median(walls),
                           'range_seconds': [min(walls), max(walls)],
                           'peak_rss_mib': max(r['timing']['peak_rss_kib'] for r in values)/1024,
                           'actual_workers': sorted(set(r['workers'] for r in values))}
    c = summary['c-one']['median_seconds']
    for config, row in summary.items():
        row['speedup_vs_c_one'] = c/row['median_seconds']
        if config.endswith('-full'):
            row['speedup_vs_same_mode_one'] = summary[config.replace('-full', '-one')]['median_seconds']/row['median_seconds']
    return summary


def main():
    os.environ['LC_ALL'] = 'C'  # Stable GNU time fields for the recorded parser.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=base.p.ROOT/'work/hg001-genome')
    parser.add_argument('--root', type=Path, default=base.p.ROOT/'work/hg001-speed')
    args = parser.parse_args(); source = args.source.resolve(); root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    with (root/'run.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock.seek(0); lock.truncate(); lock.write(str(os.getpid())); lock.flush()
        assert os.sched_getaffinity(0) == set(range(16)), 'host CPU allocation changed'
        assert 0 in cpu_list(Path('/sys/devices/cpu_core/cpus').read_text()), 'CPU 0 is not a P-core'
        frozen = json.loads((source/'frozen.json').read_text())
        source_hashes = {p: base.sha(base.p.ROOT/p) for p in SOURCES}
        manifest = {'source_hashes': source_hashes, 'binaries': frozen['binary_hashes'],
                    'input_sha256': json.loads((source/'input.json').read_text())['input_sha256'],
                    'allowed_cpus': sorted(os.sched_getaffinity(0)), 'single_cpu': 0,
                    'cpu_info': Path('/proc/cpuinfo').read_text(),
                    'schedule': schedule(),
                    'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=base.p.ROOT, text=True).strip(),
                    'diff_sha256': hashlib.sha256(subprocess.check_output(['git', 'diff'], cwd=base.p.ROOT)).hexdigest()}
        if (root/'manifest.json').exists():
            previous = json.loads((root/'manifest.json').read_text())
            for key in ['source_hashes', 'binaries', 'input_sha256', 'allowed_cpus', 'single_cpu']:
                assert previous[key] == manifest[key]
            manifest = previous
        else:
            assert manifest['diff_sha256'] == hashlib.sha256(b'').hexdigest(), 'commit protocol before launch'
            base.save(root/'manifest.json', manifest)
        run = base.Run(root)
        signal.signal(signal.SIGTERM, lambda *_: run.abort('user or external SIGTERM'))
        signal.signal(signal.SIGINT, lambda *_: run.abort('user or external SIGINT'))
        try:
            print('queued behind HG001 comparison and independent audit', flush=True)
            while not dependency_ready(source):
                if run.stop.wait(10):
                    raise RuntimeError(run.reason)
            assert base.sha(source/'HG001_GRCh38_autosomes.psmcfa') == manifest['input_sha256']
            references = {}
            for mode in ['c', 'strict', 'equivalent']:
                result = json.loads((source/f'{mode}.done.json').read_text())
                assert base.sha(source/f'{mode}.out') == result['output_sha256']
                references[mode] = (source/f'{mode}.out').read_text()
            assert base.p.numerical(references['c']) == base.p.numerical(references['strict'])
            rows = []
            for phase, config in schedule():
                assert os.sched_getaffinity(0) == set(range(16))
                assert base.sha(source/'HG001_GRCh38_autosomes.psmcfa') == manifest['input_sha256']
                for path, digest in manifest['source_hashes'].items():
                    assert base.sha(base.p.ROOT/path) == digest, f'source changed: {path}'
                for name, digest in manifest['binaries'].items():
                    assert base.sha(source/'binaries'/name) == digest
                name = f'{phase}-{config}'; mode, size = config.split('-')
                environment = root/f'{name}.host.json'
                if not (root/f'{name}.done.json').exists():
                    base.save(environment, {'before': host_sample()})
                result = dict(run.stage(name, command(source, root, name, config)))
                host = json.loads(environment.read_text())
                if 'after' not in host:
                    host['after'] = host_sample(); base.save(environment, host)
                verify_output((root/f'{name}.out').read_text(), references[mode])
                stats = None if mode == 'c' else json.loads((root/f'{name}.stats.json').read_text())
                workers = 1 if mode == 'c' or size == 'one' else 16
                if mode == 'strict':
                    workers = stats['memory_admission']['workers']
                    assert stats['memory_admission']['budget_bytes'] == 8192*1024**2
                    assert stats['memory_admission']['estimated_bytes'] <= 8192*1024**2
                assert 1 <= workers <= (1 if size == 'one' else 16)
                timing = base.timing(root/f'{name}.time')
                wall = wall_seconds((root/f'{name}.time').read_text())
                result.update(phase=phase, config=config, workers=workers, stats=stats,
                              timing=timing, wall_seconds=wall, host=host,
                              cpu_time_over_wall=(timing['user_seconds']+timing['system_seconds'])/wall,
                              output_exact=True)
                rows.append(result); base.save(root/'progress.json', base.metrics.relative(rows))
                if run.stop.wait(5):
                    raise RuntimeError(run.reason)
            report = {'manifest': manifest, 'prior_audit': json.loads((source/'audit.json').read_text()),
                      'rows': rows, 'summary': summarize(rows),
                      'scope': 'Controlled affinities, shared host; full strict may be memory-limited. Three repetitions, no truth claim.'}
            assert not run.stop.is_set(), run.reason
            base.save(root/'report.json', base.metrics.relative(report))
            print(json.dumps(report['summary'], indent=2), flush=True)
        except BaseException as exc:
            run.abort(repr(exc)); raise
        finally:
            run.close()


if __name__ == '__main__':
    main()
