#!/usr/bin/env python3
"""Matched complete human and synthetic bootstrap batches, frozen baseline vs candidate."""
import argparse
import json
import os
from pathlib import Path
import statistics
from common import ROOT, save, sha256, read_fasta, draw_bootstrap, timed_run
from phase1_differential import compare_output
from phase2_common import source_hashes, clean_env
import hg_benchmark as hg
import parallel_benchmark as parallel


def main():
    os.chdir(ROOT)
    p=argparse.ArgumentParser();p.add_argument('--candidate',required=True);p.add_argument('--report',default='bench/cpu-next-batches.json');o=p.parse_args()
    raw=Path('work/cpu-next-batches');raw.mkdir()
    binaries={'baseline':'work/cpu-next/baseline','candidate':o.candidate}
    hashes={label:sha256(binary) for label,binary in binaries.items()}
    assert hashes['baseline']=='24d47084c2914aa44109040b7f5593efb7353621cb0d36ccdb28cd1a060f4c83'
    inputs=json.loads(Path('bench/hg-input.json').read_text())
    old=json.loads(Path('bench/hg-benchmark.json').read_text())
    assert sha256(inputs['input'])==inputs['input_sha256'];assert sha256(inputs['blocks'])==inputs['blocks_sha256']
    for rep in inputs['replicates']:assert sha256(rep['path'])==rep['sha256']
    for c in old['canonical_outputs']:assert sha256(c['path'])==c['sha256']
    allowed=sorted(os.sched_getaffinity(0));assert len(allowed)==16
    scaling=json.loads(Path('bench/cpu-next-scaling.json').read_text());assert scaling['status']=='passed'
    # Choose a common configuration by the mean of BOTH paired screen times,
    # then confirm on fresh repeated batches. Do not favor the candidate alone.
    scores={w:statistics.mean(r['wall_seconds'] for r in scaling['runs'] if r['workers']==w) for w in [8,10,16]}
    workers=min(scores,key=scores.get)
    affinity=next(r['affinity'] for r in scaling['runs'] if r['workers']==workers)
    for label in binaries:assert scaling['binaries'][label]['sha256']==hashes[label]
    report=dict(status='running',runner_sha256=sha256(__file__),inherited_runners={p:sha256(p) for p in ['bench/hg_benchmark.py','bench/parallel_benchmark.py']},source_sha256=source_hashes(),binaries={label:dict(path=binary,sha256=hashes[label]) for label,binary in binaries.items()},affinity=affinity,nice=os.nice(0),runs=[],input_manifest_sha256=sha256('bench/hg-input.json'),limitations=['Matched shared-host uninstrumented complete batches; one warmup and three alternating measured pairs per workload.', 'Human chromosome 22 only; all 30 original seeds, K64 and 30 iterations retained.', 'RSS sampled at 20ms (human) or 10ms (synthetic), lower bound on peak live-process RSS; excludes controller.', 'C outputs are retained hash-verified canonical references. C timings are not rerun in this campaign.', 'Synthetic original/model-based batches retain respectively three/one nonfinite reference controls.'])
    report['worker_selection']=dict(scaling_report_sha256=sha256('bench/cpu-next-scaling.json'),paired_screen_mean_seconds=scores,selected_workers=workers,selection='Lowest mean of baseline and candidate screen wall times; identical affinity/workers used in fresh paired confirmation.')
    save(o.report,report)
    cases=[dict(id='human'),*parallel.datasets()]
    report['cases']=cases
    report['input_hashes']={path:sha256(path) for case in cases[1:] for path in [case['input'],*case['materialized'],*case['oracles']]}
    for case in cases:
        for repeat in range(4):
            for label in (['baseline','candidate'] if repeat%2==0 else ['candidate','baseline']):
                for key,binary in binaries.items():assert sha256(binary)==hashes[key]
                out=raw/f'{case["id"]}-{repeat}-{label}'
                if case['id']=='human':
                    hg.BINARIES['rust']=binaries[label];hg.EXPECTED['rust']=hashes[label]
                    run=hg.run_batch('rust',workers,inputs,out,affinity)
                    run['comparisons']=[compare_output(Path(c['path']).read_bytes(),Path(a['path']).read_bytes()) for c,a in zip(old['canonical_outputs'],run['outputs'])]
                    assert all(not r['nonfinite'] for r in run['outputs'])
                    run['all_30_exact']=True;run['finite']=30
                else:
                    run=parallel.batch(binaries[label],label,case,workers,affinity,out)
                    records=read_fasta(case['input'])
                    manifest=json.loads((out/'fits/manifest.json').read_text())
                    for i,r in enumerate(manifest['replicates']):
                        selected,draws=draw_bootstrap(records,case['seed']+i)
                        assert r['source_indices']==selected
                        actual=[json.loads(line) for line in (out/f'fits/replicate-{i:02d}.draws.jsonl').read_text().splitlines()]
                        assert actual[:-1]==[dict(event='bootstrap_draw',draw=j,**d) for j,d in enumerate(draws)]
                    run['draws_exact']=True
                    run['outputs']=[dict(index=i,path=str(out/f'fits/replicate-{i:02d}.psmc'),sha256=sha256(out/f'fits/replicate-{i:02d}.psmc')) for i in range(30)]
                    run['manifest_sha256']=sha256(out/'fits/manifest.json')
                run.update(label=label,case=case['id'],repeat=repeat,kind='warmup' if repeat==0 else 'measurement')
                report['runs'].append(run);save(o.report,report)
                print(json.dumps({k:run[k] for k in ['label','case','repeat','wall_seconds','cpu_seconds','sampled_aggregate_rss_kib','all_30_exact']}),flush=True)
    report['summary']={case['id']:{label:{field:dict(median=statistics.median(v),minimum=min(v),maximum=max(v)) for field in ['wall_seconds','cpu_seconds','sampled_aggregate_rss_kib'] for v in [[r[field] for r in report['runs'] if r['label']==label and r['case']==case['id'] and r['repeat']>0]]} for label in binaries} for case in cases}
    pilot=json.loads(Path('bench/hg-pilot.json').read_text())
    oracle=next(r for r in pilot['runs'] if r['label']=='vanilla')
    assert sha256(oracle['output'])==oracle['output_sha256']
    report['unsplit']=[]
    for label,binary in binaries.items():
        command=[binary,'--backend','cpu','--simd','auto',*hg.ARGS,inputs['input']]
        run=timed_run(command,ROOT/raw/('unsplit-'+label),env=clean_env(),timeout=600)
        assert run['exit_code']==0 and not run['nonfinite_records_beyond_initial_RI']
        run['comparison']=compare_output(Path(oracle['output']).read_bytes(),Path(run['output']).read_bytes())
        run.update(label=label,scope='Single full unsplit chromosome correctness control; not a repeated speed estimate.')
        report['unsplit'].append(run);save(o.report,report)
    assert source_hashes()==report['source_sha256']
    report['status']='passed';save(o.report,report);print(json.dumps(report['summary']),flush=True)

if __name__=='__main__':main()
