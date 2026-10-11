#!/usr/bin/env python3
"""Explicit continuation after the recorded preflight pause; never rerun completed fits.
The original runner, protocol, inputs and executables remain frozen. Wait for the
original resource floor before starting each missing stage. Any new failure stops.
"""
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import adoption_qualification as campaign

ROOT, OUT, GIB = campaign.ROOT, campaign.OUT, campaign.GIB


def checked_prior():
    frozen = json.loads((OUT / 'frozen.json').read_text())
    partial = json.loads((ROOT / 'bench/adoption-qualification-partial.json').read_text())
    assert campaign.sha(OUT / 'failure.json') == partial['failure_sha256']
    assert partial['failure']['error'] == "AssertionError('preflight resource floor')"
    assert not (OUT / 'stop.json').exists()
    assert not (OUT / 'equivalent').exists()
    assert sorted(p.name for p in OUT.glob('*.done.json')) == ['bootstrap-strict.done.json', 'split.done.json']
    assert campaign.sha(OUT / 'strict/manifest.json') == partial['strict_manifest_sha256']
    for name, digest in partial['strict_hashes_verified'].items():
        assert campaign.sha(ROOT / name) == digest
    for name, digest in frozen['binary_hashes'].items():
        assert campaign.sha(OUT / 'binaries' / name) == digest
    for name, digest in frozen['input_sha256'].items():
        assert campaign.sha(ROOT / name) == digest
    for name, key in [('docs/adoption-qualification-protocol.md', 'protocol_sha256'), ('bench/adoption_qualification.py', 'runner_sha256')]:
        assert campaign.sha(ROOT / name) == frozen[key]
    for name in ['bench/known_truth.py', 'bench/known_truth_200mb.py', 'bench/hg001_genome_run.py']:
        assert (ROOT / name).read_bytes() == subprocess.check_output(['git', 'show', f"{frozen['commit']}:{name}"], cwd=ROOT)
    return frozen, partial


def remaining():
    binary = OUT / 'binaries/rust'
    yield 'bootstrap-equivalent', [binary, 'bootstrap', '--mode', 'equivalent', '--seed', str(campaign.SEED), '--replicates', '30', '--workers', '16', '--memory-mib', '8192', '--progress', '--output-dir', OUT / 'equivalent', *campaign.p.FIT, OUT / 'blocks.psmcfa']
    for dataset, input_file in [('hg001-chr22', ROOT / 'work/hg001-genome/chromosomes/chr22.psmcfa'), ('hg002-chr1', campaign.HG002)]:
        for pattern in ['4+5*3+4', '8+8+8+8']:
            fit = ['-p', pattern, '-N', '30', '-t', '15', '-r', '5', '-I', '0']
            for mode in ['c-o2', 'c-fma', 'strict', 'equivalent']:
                name = dataset + '-' + pattern.replace('*', 'x') + '-' + mode
                command = ['/usr/bin/taskset', '-c', str(min(os.sched_getaffinity(0))), OUT / 'binaries' / mode, *fit, input_file] if mode.startswith('c-') else [binary, '--mode', mode, '--seed', str(campaign.SEED), '--record-workers', '4', '--memory-mib', '4096', '--stats', OUT / (name + '.stats.json'), *fit, input_file]
                yield name, command


def main():
    with (OUT / 'run.lock').open('r+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Refuse a second continuation, including one after an incomplete attempt.
        with (OUT / 'continuation.json').open('x') as record:
            frozen, partial = checked_prior()
            state = dict(status='waiting_for_resources', created=time.time(), pid=os.getpid(),
                         source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                         continuation_sha256=campaign.sha(__file__),
                         frozen_commit=frozen['commit'], preserved_failure_sha256=partial['failure_sha256'],
                         preserved_strict_manifest_sha256=partial['strict_manifest_sha256'],
                         original_failure='Preflight RAM/disk floor before equivalent; no equivalent stage started',
                         policy='Wait for unchanged 14 GiB RAM and 25 GiB disk; no rerun or weaker guard', stages=[])
            json.dump(state, record, indent=2)
        lock.seek(0); lock.truncate(); lock.write(str(os.getpid())); lock.flush()
        deadline = time.monotonic() + 12 * 3600
        def save(): campaign.save(OUT / 'continuation.json', state)
        def stopped(*_): raise RuntimeError('continuation interrupted while waiting')
        try:
            for name, command in remaining():
                signal.signal(signal.SIGTERM, stopped); signal.signal(signal.SIGINT, stopped)
                state.update(status='waiting_for_resources', next_stage=name); save()
                while True:
                    ram = campaign.available(); disk = shutil.disk_usage(OUT).free
                    if time.monotonic() > deadline: raise RuntimeError('12-hour continuation deadline')
                    if disk < 25 * GIB: raise RuntimeError('disk floor during continuation wait')
                    if ram >= 14 * GIB: break
                    time.sleep(15)
                state.update(status='running', next_stage=name)
                state['stages'].append(dict(name=name, preflight_time=time.time(), available_ram=ram, free_disk=disk))
                save()
                campaign.stage(name, command)  # Original unmodified hard limits, guards and timings.
            campaign.analyze()
            state.update(status='completed', completed=time.time(), next_stage=None); save()
        except BaseException as error:
            state.update(status='failed', error=repr(error), failed=time.time()); save()
            raise


if __name__ == '__main__':
    main()
