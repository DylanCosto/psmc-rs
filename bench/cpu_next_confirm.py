#!/usr/bin/env python3
"""Fixed opposite-order confirmation after the first two paired results disagreed."""
import json,os,statistics
from pathlib import Path
from common import ROOT,save,sha256
from phase1_differential import compare_output
import hg_benchmark as hg

def main():
    os.chdir(ROOT);main=json.loads(Path('bench/cpu-next-batches.json').read_text());assert main['status']=='passed'
    raw=Path('work/cpu-next/confirmation');raw.mkdir()
    inputs=json.loads(Path('bench/hg-input.json').read_text());oracles=json.loads(Path('bench/hg-benchmark.json').read_text())['canonical_outputs']
    for r in inputs['replicates']:assert sha256(r['path'])==r['sha256']
    for c in oracles:assert sha256(c['path'])==c['sha256']
    assert sha256(inputs['blocks'])==inputs['blocks_sha256']
    report=dict(status='running',runner_sha256=sha256(__file__),primary_report_sha256=sha256('bench/cpu-next-batches.json'),binaries=main['binaries'],runs=[],affinity=main['affinity'],workers=main['worker_selection']['selected_workers'],design='Fixed one-warmup plus three opposite-order paired human batches, specified after the first two primary measured pairs disagreed on wall/CPU direction. No further repetitions selected by outcome; preserve and pool all six measured pairs. All 30 seeds, K64/N30 and exact C checks unchanged.')
    for repeat in range(4):
        for label in (['candidate','baseline'] if repeat%2==0 else ['baseline','candidate']):
            entry=report['binaries'][label];assert sha256(entry['path'])==entry['sha256'];hg.BINARIES['rust']=entry['path'];hg.EXPECTED['rust']=entry['sha256']
            run=hg.run_batch('rust',report['workers'],inputs,raw/f'{repeat}-{label}',report['affinity'])
            run['comparisons']=[compare_output(Path(c['path']).read_bytes(),Path(a['path']).read_bytes()) for c,a in zip(oracles,run['outputs'])]
            assert all(not v['nonfinite'] for v in run['outputs']);run.update(label=label,repeat=repeat,kind='warmup' if repeat==0 else 'measurement',all_30_exact=True)
            report['runs'].append(run);save('bench/cpu-next-confirmation.json',report);print(json.dumps({k:run[k] for k in ['label','repeat','wall_seconds','cpu_seconds','sampled_aggregate_rss_kib']}),flush=True)
    pooled=[r for r in main['runs'] if r['case']=='human']+report['runs']
    report['pooled_summary']={label:{field:dict(median=statistics.median(v),minimum=min(v),maximum=max(v)) for field in ['wall_seconds','cpu_seconds','sampled_aggregate_rss_kib'] for v in [[r[field] for r in pooled if r['label']==label and r['repeat']>0]]} for label in main['binaries']}
    pairs=[]
    for block,runs in [('primary',[r for r in main['runs'] if r['case']=='human']),('confirmation',report['runs'])]:
        for rep in range(1,4):
            b=next(r for r in runs if r['label']=='baseline' and r['repeat']==rep);c=next(r for r in runs if r['label']=='candidate' and r['repeat']==rep)
            pairs.append(dict(block=block,repeat=rep,wall_reduction_percent=100*(1-c['wall_seconds']/b['wall_seconds']),cpu_reduction_percent=100*(1-c['cpu_seconds']/b['cpu_seconds'])))
    report['paired_effects']=pairs;report['status']='passed';save('bench/cpu-next-confirmation.json',report);print(json.dumps(dict(pooled_summary=report['pooled_summary'],paired_effects=pairs)),flush=True)
if __name__=='__main__':main()
