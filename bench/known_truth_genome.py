#!/usr/bin/env python3
"""Frozen 3 Gb panel with bounded children, verified retention and stage resume."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time

import known_truth as p
import known_truth_200mb as metrics

ROOT = p.ROOT
GIB = 1024**3
LENGTHS = [250_000_000] + [120_000_000]*22 + [110_000_000]
HISTORIES = metrics.HISTORIES
SOURCES = ['bench/known_truth_genome.py', 'bench/known_truth.py',
           'bench/known_truth_200mb.py', 'docs/known-truth-genome-protocol.md']


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024**2), b''): h.update(chunk)
    return h.hexdigest()


def save(path, data):
    path = Path(path)
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


def seeds(history, index, chromosome):
    q = 24*(list(HISTORIES).index(history)*10+index)+chromosome
    return [41001+q, 43001+3*q, 47001+7*q]


def available():
    values = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    host = int(values['MemAvailable'].split()[0])*1024
    # Same conservative effective-headroom principle as production admission.
    for line in Path('/proc/self/cgroup').read_text().splitlines():
        hierarchy, controllers, relative = line.split(':', 2)
        if hierarchy == '0' and not controllers:
            mount = Path('/sys/fs/cgroup')
            current = mount/relative.lstrip('/')
            while current.is_relative_to(mount):
                try:
                    limit = (current/'memory.max').read_text().strip()
                    used = int((current/'memory.current').read_text())
                    if limit != 'max': host = min(host, max(0, int(limit)-used))
                except (OSError, ValueError): pass
                if current == mount: break
                current = current.parent
    return host


def disk_bytes(root):
    total = 0
    for directory, _, names in os.walk(root):
        for name in names:
            try: total += (Path(directory)/name).stat().st_size
            except FileNotFoundError: pass
    return total


def compressed_sha(path):
    h = hashlib.sha256()
    with gzip.open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024**2), b''): h.update(chunk)
    return h.hexdigest()


def compress_verified(path):
    original = sha(path)
    dest = Path(str(path)+'.gz')
    temporary = Path(str(dest)+'.tmp')
    with path.open('rb') as src, gzip.open(temporary, 'wb', compresslevel=6) as dst:
        shutil.copyfileobj(src, dst, 1024**2)
    assert compressed_sha(temporary) == original
    temporary.replace(dest)
    path.unlink()  # Only the verified redundant uncompressed ms output.
    return {'original_sha256': original, 'gzip_sha256': sha(dest)}


def child_launch():
    # Run resource setup in a fresh single-threaded process, never preexec_fn.
    ceiling = int(sys.argv[2])*GIB
    resource.setrlimit(resource.RLIMIT_AS, (ceiling, ceiling))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2*GIB, 2*GIB))
    os.nice(10)
    os.execv(sys.argv[3], sys.argv[3:])


class Runner:
    def __init__(self, root):
        self.root = root
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.finished = threading.Event()
        self.active = {}
        self.reason = None
        self.monitor = threading.Thread(target=self.watch, daemon=True)
        self.monitor.start()

    def abort(self, reason):
        with self.lock:
            if not self.reason:
                self.reason = reason
                save(self.root/'resource-stop.json', {'reason': reason, 'time': time.time()})
            self.stop.set()
            for pid in self.active:
                try: os.killpg(pid, signal.SIGTERM)
                except ProcessLookupError: pass

    def watch(self):
        try:
            with (self.root/'resources.jsonl').open('a', buffering=1) as log:
                while not self.finished.is_set():
                    free = shutil.disk_usage(self.root).free
                    ram = available()
                    size = disk_bytes(self.root)
                    with self.lock: jobs = dict(self.active)
                    rss = {pid: 0 for pid in jobs}
                    for proc in Path('/proc').iterdir():
                        if not proc.name.isdigit(): continue
                        try:
                            fields = (proc/'stat').read_text().rsplit(')', 1)[1].split()
                            group = int(fields[2])
                            if group in rss:
                                pages = int((proc/'statm').read_text().split()[1])
                                rss[group] += pages*os.sysconf('SC_PAGE_SIZE')
                        except (OSError, ValueError, IndexError): pass
                    log.write(json.dumps({'time': time.time(), 'free_disk': free,
                        'available_ram': ram, 'panel_bytes': size,
                        'jobs': jobs, 'group_rss_bytes': rss})+'\n')
                    if free < 25*GIB or ram < 4*GIB or size > 12*GIB:
                        self.abort(f'resource floor: disk={free}, available={ram}, panel={size}')
                    if self.stop.is_set():
                        for pid in jobs:
                            try: os.killpg(pid, signal.SIGKILL)
                            except ProcessLookupError: pass
                    self.finished.wait(2)
        except BaseException as e:
            self.abort('monitor failed: '+repr(e))

    def stage(self, base, command, ceiling=6, min_ram=10):
        base = Path(base)
        done = Path(str(base)+'.done.json')
        output = Path(str(base)+'.out')
        compressed = Path(str(output)+'.gz')
        if done.exists():
            result = json.loads(done.read_text())
            assert result['command'] == list(map(str, command)), 'resume command differs'
            digest = sha(output) if output.exists() else compressed_sha(compressed)
            assert digest == result['output_sha256'], 'completed output changed'
            return result
        # Preserve partial previous attempts before exact-stage retries.
        attempt = 0
        while Path(str(base)+f'.attempt-{attempt}.json').exists(): attempt += 1
        for suffix in ['.out', '.stderr', '.time']:
            path = Path(str(base)+suffix)
            if path.exists(): path.rename(Path(str(base)+f'.partial-{attempt}'+suffix))
        while not self.stop.is_set():
            if shutil.disk_usage(self.root).free >= 30*GIB and available() >= min_ram*GIB: break
            self.stop.wait(2)
        if self.stop.is_set(): raise RuntimeError(self.reason)
        wrapper = [sys.executable, str(Path(__file__).resolve()), '--child-launch', str(ceiling),
                   '/usr/bin/time', '-v', '-o', str(base)+'.time', *map(str, command)]
        start = time.time()
        with output.open('w') as out, Path(str(base)+'.stderr').open('w') as err:
            process = subprocess.Popen(wrapper, cwd=base.parent, stdout=out, stderr=err,
                                       start_new_session=True)
            with self.lock: self.active[process.pid] = str(base.relative_to(self.root))
            save(Path(str(base)+f'.attempt-{attempt}.json'), {'pid': process.pid,
                'started': start, 'command': list(map(str, command)), 'ceiling_gib': ceiling})
            try:
                while process.poll() is None:
                    if self.stop.wait(1) or time.time()-start > 86400:
                        if not self.stop.is_set(): self.abort('24-hour stage timeout: '+str(base))
                        try: os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError: pass
                        break
                code = process.wait()
            finally:
                with self.lock: self.active.pop(process.pid, None)
        result = {'command': list(map(str, command)), 'seconds': time.time()-start,
                  'exit_code': code, 'output_sha256': sha(output), 'ceiling_gib': ceiling}
        save(Path(str(base)+f'.attempt-{attempt}.json'), result)
        if code != 0 or self.stop.is_set():
            raise RuntimeError(f'{base.name}: exit {code}; {self.reason}')
        save(done, result)
        print('completed', base.relative_to(self.root), flush=True)
        return result

    def close(self):
        self.finished.set()
        self.monitor.join()


def validate_input(path, lengths=LENGTHS):
    sizes, current = [], None
    with path.open() as f:
        for line in f:
            if line.startswith('>'):
                if current is not None: sizes.append(current)
                current = 0
            else:
                sequence = line.strip()
                assert current is not None and set(sequence) <= set('TK')
                current += len(sequence)
    if current is not None: sizes.append(current)
    assert sizes == [x//100 for x in lengths], sizes
    return sizes


def case(runner, name, index, binaries):
    folder = runner.root/f'{name}-{index:02}'
    folder.mkdir(exist_ok=True)
    final = folder/'result.json'
    if final.exists():
        prior = json.loads(final.read_text())
        if prior['status'] == 'complete':
            assert sha(folder/'input.psmcfa') == prior['input_sha256']
            for mode in ['c', 'strict', 'equivalent']:
                assert sha(folder/f'{mode}.out') == prior['runs'][mode]['output_sha256']
            return prior
    try:
        history = HISTORIES[name]
        history_file = folder/'truth.history'
        text = 'T 0.1\nR 0.02\n'+''.join(f'H {t/20000:.12g} {n/10000:.12g}\n' for t,n in history)
        if history_file.exists(): assert history_file.read_text() == text
        else: history_file.write_text(text)
        simulations = []
        for k, length in enumerate(LENGTHS):
            base = folder/f'chr-{k:02}'
            fasta = Path(str(base)+'.psmcfa')
            manifest = Path(str(base)+'.converted.json')
            emitted = subprocess.check_output(['perl', str(binaries['history2ms']), '-L',
                str(length), '-r', '1', '-u', str(p.MU), str(history_file)], text=True).strip()
            args = shlex.split(emitted)
            assert args[:3] == ['msHOT-lite', '2', '1'] and args.count('-l') == 1
            triple = seeds(name, index, k)
            command = [str(binaries['ms']), *[a for a in args[1:] if a != '-l'],
                       '-p', '12', '-seeds', *map(str, triple)]
            simulation = runner.stage(base, command)
            raw = Path(str(base)+'.out')
            if not manifest.exists():
                if raw.exists(): raw_text = raw.read_text()
                else:
                    with gzip.open(str(raw)+'.gz', 'rt') as f: raw_text = f.read()
                encoded = p.convert_ms(raw_text, length=length, bin_size=100, expected=1)
                encoded = encoded.replace('>ms-1\n', f'>chr-{k+1}\n', 1)
                fasta.write_text(encoded)
                validate_input(fasta, [length])
                compression = compress_verified(raw) if raw.exists() else {
                    'original_sha256': compressed_sha(str(raw)+'.gz'),
                    'gzip_sha256': sha(str(raw)+'.gz')}
                save(manifest, {'length': length, 'seeds': triple,
                    'history2ms_command': emitted, 'fasta_sha256': sha(fasta),
                    'compression': compression, 'run': simulation})
            record = json.loads(manifest.read_text())
            assert record['length'] == length and record['seeds'] == triple
            assert record['fasta_sha256'] == sha(fasta)
            assert record['compression']['gzip_sha256'] == sha(str(raw)+'.gz')
            simulations.append(record)
        encoded = folder/'input.psmcfa'
        if not encoded.exists():
            temporary = folder/'input.psmcfa.tmp'
            with temporary.open('wb') as dst:
                for k in range(24):
                    with (folder/f'chr-{k:02}.psmcfa').open('rb') as src:
                        shutil.copyfileobj(src, dst, 1024**2)
            temporary.replace(encoded)
        validate_input(encoded)
        runs, texts, params, curves = {}, {}, {}, {}
        for mode in ['c', 'strict', 'equivalent']:
            command = [str(binaries['c']), *p.FIT] if mode == 'c' else [
                str(binaries['rust']), '--mode', mode, '--record-workers',
                '1' if mode == 'strict' else '4', '--stats', str(folder/f'{mode}.stats.json'),
                *(['--memory-mib', '4096'] if mode == 'strict' else []), *p.FIT]
            runs[mode] = runner.stage(folder/mode, [*command, str(encoded)])
            texts[mode] = (folder/f'{mode}.out').read_text()
            curves[mode], params[mode] = p.curve(texts[mode])
        bands = {band: metrics.curve_metrics(params, history, *limits)
                 for band, limits in metrics.BANDS.items()}
        record = {'history': name, 'index': index, 'status': 'complete',
            'lengths': LENGTHS, 'simulations': simulations, 'input_sha256': sha(encoded),
            'runs': runs, 'strict_c_exact': p.numerical(texts['c']) == p.numerical(texts['strict']),
            'parameters': params, 'bands': bands,
            'event_ratios': {mode: metrics.event_ratio(v, name) for mode,v in params.items()},
            'full_grid_rmse': {mode: p.rmse(c, [metrics.truth(history,t) for t in p.GRID])
                               for mode,c in curves.items()},
            'stats': {mode: json.loads((folder/f'{mode}.stats.json').read_text())
                      for mode in ['strict', 'equivalent']}, 'ridge': None}
        if any(b['mode_curve_rmse'] > .01 for b in bands.values()):
            runner.stage(folder/'ridge', [str(binaries['ridge']), str(encoded),
                         str(folder/'strict.out'), str(folder/'equivalent.out')])
            record['ridge'] = [json.loads(line) for line in (folder/'ridge.out').read_text().splitlines()]
        save(final, record)
        return record
    except Exception as e:
        record = {'history': name, 'index': index, 'status': 'incomplete', 'error': repr(e)}
        save(folder/f'incomplete-{time.time_ns()}.json', record)
        runner.abort(f'{name}-{index:02}: '+repr(e))
        return record


def freeze(root):
    paths = {'ms': ROOT/'work/qualification/msdir/ms', 'c': ROOT/'work/vanilla/psmc',
             'rust': ROOT/'bin/psmc-rs', 'ridge': ROOT/'target/release/examples/equivalent_ridge',
             'history2ms': ROOT/'work/vanilla/utils/history2ms.pl'}
    hashes = {name: sha(ROOT/name) for name in SOURCES}
    frozen = root/'frozen.json'
    if frozen.exists():
        meta = json.loads(frozen.read_text())
        assert meta['source_hashes'] == hashes, 'frozen protocol/runner/helper changed'
        for name, digest in meta['binary_hashes'].items():
            assert sha(root/'binaries'/name) == digest
    else:
        (root/'binaries').mkdir()
        for name, source in paths.items(): shutil.copy2(source, root/'binaries'/name)
        meta = {'source_hashes': hashes, 'binary_hashes': {n: sha(s) for n,s in paths.items()},
                'source_commit': subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT,text=True).strip(),
                'source_diff_sha256': hashlib.sha256(subprocess.check_output(['git','diff'],cwd=ROOT)).hexdigest(),
                'created': time.time(), 'lengths': LENGTHS, 'histories': HISTORIES,
                'fit_args': p.FIT, 'jobs': 2}
        save(frozen, meta)
    return meta, {n: root/'binaries'/n for n in paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    with (root/'run.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock.write(str(os.getpid())+'\n'); lock.flush()
        meta, binaries = freeze(root)
        runner = Runner(root)
        signal.signal(signal.SIGTERM, lambda *_: runner.abort('harness SIGTERM'))
        signal.signal(signal.SIGINT, lambda *_: runner.abort('harness SIGINT'))
        try:
            results = []
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(case, runner, h, i, binaries) for h in HISTORIES for i in range(10)]
                for future in as_completed(futures):
                    result = future.result(); results.append(result)
                    print(result['history'], result['index'], result['status'], flush=True)
            results.sort(key=lambda r: (r['history'], r['index']))
            if runner.stop.is_set(): raise RuntimeError(runner.reason)
            mainfit = root/'constant-00'
            concurrent = runner.stage(mainfit/'strict-concurrent', [str(binaries['rust']),
                '--mode','strict','--record-workers','16','--memory-mib','8192',
                '--stats',str(mainfit/'strict-concurrent.stats.json'), *p.FIT,
                str(mainfit/'input.psmcfa')], ceiling=10, min_ram=14)
            concurrent['output_exact'] = (mainfit/'strict-concurrent.out').read_bytes() == (mainfit/'strict.out').read_bytes()
            concurrent['stats'] = json.loads((mainfit/'strict-concurrent.stats.json').read_text())
            concurrent['passed'] = concurrent['output_exact'] and concurrent['stats']['memory_admission']['workers'] >= 2
            summary = metrics.summarize(results)
            report = metrics.relative({'metadata': meta, 'summary': summary, 'cases': results,
                'concurrent_check': concurrent, 'scientific_passed': all(s['passed'] for s in summary.values()),
                'resource_check_passed': not runner.stop.is_set(),
                'passed': all(s['passed'] for s in summary.values()) and concurrent['passed']})
            save(root/'report.json', report)
            print(json.dumps({k:v for k,v in report.items() if k in ['summary','passed','scientific_passed']},indent=2), flush=True)
        finally: runner.close()


if __name__ == '__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--child-launch': child_launch()
    else: main()
