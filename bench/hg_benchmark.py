#!/usr/bin/env python3
"""Complete human-fixture bootstrap timing and exactness; no reduced trajectories."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import resource
import statistics
import subprocess
import time
from common import ROOT, nonfinite_records, save, sha256
from phase1_differential import compare_output
from phase2_common import clean_env, source_hashes
from parallel_benchmark import rss

ARGS = ['-p', '4+25*2+4+6', '-N', '30', '-t', '15', '-r', '5', '-I', '0']
BINARIES = {'rust': 'bin/psmc-rs', 'vanilla': 'work/vanilla/psmc'}
EXPECTED = {'rust': 'b0fc39d7c31637221de1152fc0d502bb65c90d0a5b9d6672250fe3117f75bfa4', 'vanilla': 'da1743512f1925da6277d5a2e5350c70c61c9771d11749df0918605f795ff32b'}

def cpu_seconds():
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    return r.ru_utime + r.ru_stime


def run_batch(label, workers, inputs, output, affinity):
    output.mkdir()
    if label == 'vanilla':
        commands = [[BINARIES[label], '-o', str(output / f'replicate-{i:02d}.psmc'), *ARGS, rep['path']] for i, rep in enumerate(inputs['replicates'])]
    else:
        commands = [[BINARIES[label], 'bootstrap', '--backend', 'cpu', '--simd', 'auto', '--workers', str(workers), '--replicates', '30', '--memory-mib', '4096', '--seed', str(inputs['seed']), '--output-dir', str(output / 'fits'), *ARGS, inputs['blocks']]]
    for key, binary in BINARIES.items():
        assert sha256(binary) == EXPECTED[key]
    pending = list(enumerate(commands))
    active = []
    peak_rss = 0
    concurrent = 0
    completed = []
    before_cpu = cpu_seconds()
    start = time.perf_counter()
    next_update = start + 30
    try:
        while pending or active:
            while pending and len(active) < workers:
                i, command = pending.pop(0)
                stdout = (output / f'child-{i}.stdout').open('wb')
                stderr = (output / f'child-{i}.stderr').open('wb')
                begun = time.perf_counter()
                p = subprocess.Popen(command, env=clean_env(), stdout=stdout, stderr=stderr, preexec_fn=lambda: os.sched_setaffinity(0, affinity))
                active.append((i, p, stdout, stderr, begun))
            concurrent = max(concurrent, len(active))
            peak_rss = max(peak_rss, sum(rss(p.pid) for _, p, _, _, _ in active))
            remaining = []
            for i, p, stdout, stderr, begun in active:
                rc = p.poll()
                if rc is None:
                    remaining.append((i, p, stdout, stderr, begun))
                else:
                    stdout.close(); stderr.close()
                    assert rc == 0, (label, i, rc)
                    completed.append(dict(index=i, wall_seconds=time.perf_counter()-begun))
            active = remaining
            now = time.perf_counter()
            if now >= next_update:
                fitdir = output / 'fits' if label == 'rust' else output
                print(json.dumps(dict(progress=str(output),elapsed_seconds=now-start,processes_finished=len(completed),output_files=len(list(fitdir.glob('replicate-*.psmc'))))), flush=True)
                next_update = now + 30
            if active:
                time.sleep(.02)
    finally:
        for _, p, stdout, stderr, _ in active:
            if p.poll() is None:
                p.terminate(); p.wait()
            stdout.close(); stderr.close()
    result = dict(label=label,workers=workers,affinity=affinity,commands=commands,wall_seconds=time.perf_counter()-start,cpu_seconds=cpu_seconds()-before_cpu,sampled_aggregate_rss_kib=peak_rss,max_concurrent_processes=concurrent,output_directory=str(output),individual_process_elapsed=completed,load_average=list(os.getloadavg()))
    fits = output / 'fits' if label == 'rust' else output
    result['outputs'] = [dict(index=i,path=str(fits / f'replicate-{i:02d}.psmc'),sha256=sha256(fits / f'replicate-{i:02d}.psmc'),nonfinite=nonfinite_records((fits / f'replicate-{i:02d}.psmc').read_text())) for i in range(30)]
    if label == 'rust':
        manifest = json.loads((fits / 'manifest.json').read_text())
        assert manifest['workers'] == workers and manifest['failed_replicates'] == 0
        assert [r['index'] for r in manifest['replicates']] == list(range(30))
        for i, rep in enumerate(inputs['replicates']):
            assert json.loads((fits / f'replicate-{i:02d}.stats.json').read_text())['simd_selected'] == 'avx'
            draws = [json.loads(line) for line in (fits / f'replicate-{i:02d}.draws.jsonl').read_text().splitlines()]
            expected_draws = [dict(event='bootstrap_draw', draw=j, **d) for j, d in enumerate(rep['draws'])]
            assert draws[:-1] == expected_draws, (i, 'draw mismatch')
            assert draws[-1] == dict(event='bootstrap_end', accepted_sequences=len(rep['indices']), length=rep['draws'][-1]['after_length'], target_length=inputs['bins'])
            assert manifest['replicates'][i]['source_indices'] == rep['indices']
        result['manifest_sha256'] = sha256(fits / 'manifest.json')
        result['actual_workers'] = manifest['workers']
        result['draws_exact'] = True
    return result


def main():
    os.chdir(ROOT)
    p=argparse.ArgumentParser();p.add_argument('--repeats',type=int,default=3);o=p.parse_args()
    assert o.repeats >= 3
    inputs=json.loads(Path('bench/hg-input.json').read_text())
    assert sha256(inputs['input']) == inputs['input_sha256']
    assert sha256(inputs['blocks']) == inputs['blocks_sha256']
    for rep in inputs['replicates']: assert sha256(rep['path']) == rep['sha256']
    affinity=sorted(os.sched_getaffinity(0)); assert len(affinity)==16, 'This recorded matrix targets the tested 16-CPU host.'
    raw=Path('bench/hg')/('batches-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));raw.mkdir()
    report=dict(status='running',runner_sha256=sha256(__file__),input_manifest_sha256=sha256('bench/hg-input.json'),source_sha256=source_hashes(),binaries={k:dict(path=v,sha256=EXPECTED[k]) for k,v in BINARIES.items()},args=ARGS,raw_directory=str(raw),allowed_cpus=affinity,nice=os.nice(0),memory_budget_mib=4096,runs=[],limitations=['Shared-host measurements; all complete benchmark groups run sequentially.', 'RSS sampled every 20 ms across live child processes, excludes controller; lower bound on peak.', 'Single-chromosome upstream public fixture, raw calling provenance not independently established.', 'All 30 seeds retained. Full 64-state 30-iteration trajectories in every run.', '8/10-worker screens each run once and are exploratory; the repeated matched comparison is fixed at 16 workers.'])
    save('bench/hg-benchmark.json',report)
    canonical=None
    schedule=[('vanilla',16,'warmup',0),('rust',16,'warmup',0),('rust',8,'screen',0),('rust',10,'screen',0)]
    for rep in range(1,o.repeats+1):
        for label in (['rust','vanilla'] if rep%2 else ['vanilla','rust']):schedule.append((label,16,'measurement',rep))
    for label,workers,kind,rep in schedule:
        name=f'{kind}-{rep}-{label}-w{workers}'
        run=run_batch(label,workers,inputs,raw/name,affinity)
        if canonical is None:
            canonical=run['outputs']
            report['canonical_outputs']=canonical
        run['comparisons']=[compare_output(Path(c['path']).read_bytes(),Path(a['path']).read_bytes()) for c,a in zip(canonical,run['outputs'])]
        run.update(kind=kind,repeat=rep,all_30_exact=True,finite=sum(not r['nonfinite'] for r in run['outputs']))
        report['runs'].append(run);save('bench/hg-benchmark.json',report)
        print(json.dumps({k:run[k] for k in ['label','workers','kind','repeat','wall_seconds','cpu_seconds','sampled_aggregate_rss_kib','finite','all_30_exact']}),flush=True)
    report['summary']={label:{field:dict(median=statistics.median(v),minimum=min(v),maximum=max(v)) for field in ['wall_seconds','cpu_seconds','sampled_aggregate_rss_kib'] for v in [[r[field] for r in report['runs'] if r['label']==label and r['kind']=='measurement']]} for label in BINARIES}
    assert source_hashes()==report['source_sha256']
    report['status']='passed';save('bench/hg-benchmark.json',report)
    print(json.dumps(report['summary']),flush=True)

if __name__=='__main__':main()
