#!/usr/bin/env python3
"""Bounded candidate resource/whole-genome regression; no new genomic data."""
import argparse
import json
from pathlib import Path
import signal
import hg001_genome_run as base


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); root = a.output.resolve(); root.mkdir(parents=True, exist_ok=False)
    binary = a.binary.resolve(); runner = base.Run(root)
    signal.signal(signal.SIGTERM, lambda *_: runner.abort('external SIGTERM'))
    signal.signal(signal.SIGINT, lambda *_: runner.abort('external SIGINT'))
    rows = []
    try:
        fixture = base.p.ROOT/'work/qualification/memory-rss-final/eight-million-bins.psmcfa'
        cases = [('strict-memory', ['--mode', 'strict', '--memory-mib', '2048'], fixture, 2),
                 ('equivalent-decode', ['--memory-mib', '3500', '-d'], fixture, 2),
                 ('hg001-default', ['--memory-mib', '8192'], base.p.ROOT/'work/hg001-genome/HG001_GRCh38_autosomes.psmcfa', 30)]
        for name, extra, inp, iterations in cases:
            stats = root/f'{name}.stats.json'
            cmd = [str(binary), '--record-workers', '16', '--stats', str(stats),
                   '-p', '4+25*2+4+6', '-N', str(iterations), '-t', '15', '-r', '5', '-I', '0', '--seed', '42', *extra, str(inp)]
            row = runner.stage(name, cmd)
            metadata = json.loads(stats.read_text()); admission = metadata['memory_admission']
            assert admission['estimated_bytes'] <= admission['budget_bytes']
            assert metadata['mode'] == ('strict' if name == 'strict-memory' else 'equivalent')
            assert not metadata['nonfinite_output']
            timing = base.timing(root/f'{name}.time')
            assert timing['peak_rss_kib']*1024 < admission['budget_bytes']
            reference = None
            if name == 'strict-memory':
                reference = base.p.ROOT/'work/qualification/memory-rss-final/bounded_serial.psmc'
                assert admission['workers'] == 1
            if name == 'hg001-default':
                reference = base.p.ROOT/'work/hg001-genome/equivalent.out'
                assert admission['workers'] == 16
            if reference:
                assert base.p.numerical((root/f'{name}.out').read_text()) == base.p.numerical(reference.read_text())
            rows.append({**row, 'name': name, 'stats': metadata, 'timing': timing,
                         'input_sha256': base.sha(inp), 'reference_exact': True if reference else None})
        runner.close()
        samples = [json.loads(l) for l in (root/'resources.jsonl').read_text().splitlines()]
        assert not runner.stop.is_set()
        report = {'passed': True, 'binary_sha256': base.sha(binary), 'runs': rows,
                  'min_available_ram_gib': min(s['available_ram'] for s in samples)/base.GIB,
                  'min_free_disk_gib': min(s['free_disk'] for s in samples)/base.GIB,
                  'scope': 'Bounded allocation/decoding and whole-HG001 parity, not a new speed benchmark.'}
        base.save(root/'report.json', base.metrics.relative(report))
        print(json.dumps({'passed': True, 'runs': len(rows)}), flush=True)
    except BaseException as e:
        runner.abort(repr(e)); raise
    finally: runner.close()


if __name__ == '__main__': main()
