#!/usr/bin/env python3
"""Read-only delivery audit and derived optimization report."""
import json
import os
from pathlib import Path
import re
from common import ROOT, save, sha256
from phase1_differential import compare_output
from cpu_campaign_build import source_hashes


def main():
    os.chdir(ROOT)
    names=['screen','generator','gates','validation','extended','scheduler','review','batches','build','capacity']
    reports={k:json.loads(Path(f'bench/counts-{k}.json').read_text()) for k in names}
    for k,r in reports.items():assert r['status']==('built' if k=='build' else 'passed'),k
    build=reports['build'];batch=reports['batches'];gate=reports['validation']
    assert source_hashes()==build['source_sha256']
    candidate=build['rust_binary']['sha256']
    assert sha256('target/release/psmc-rs')==sha256('bin/psmc-rs')==candidate
    assert sha256('bin/psmc-rs-v0.3.1')==batch['binaries']['baseline']['sha256']
    assert candidate==batch['binaries']['candidate']['sha256']==gate['provenance']['binaries']['candidate']['sha256']
    checks=0
    human=json.loads(Path('bench/hg-benchmark.json').read_text())['canonical_outputs']
    cases={c['id']:c for c in batch['cases']}
    for run in batch['runs']:
        oracles=human if run['case']=='human' else [dict(path=p,sha256=batch['input_hashes'][p]) for p in cases[run['case']]['oracles']]
        for c,a in zip(oracles,run['outputs']):
            assert sha256(c['path'])==c['sha256'];assert sha256(a['path'])==a['sha256']
            compare_output(Path(c['path']).read_bytes(),Path(a['path']).read_bytes());checks+=1
    for path,digest in batch['input_hashes'].items():assert sha256(path)==digest
    assert checks==720 and len(batch['unsplit'])==2
    pilot=json.loads(Path('bench/hg-pilot.json').read_text())['runs'][0]
    assert sha256(pilot['output'])==pilot['output_sha256']
    for run in batch['unsplit']:
        assert sha256(run['output'])==run['output_sha256']
        compare_output(Path(pilot['output']).read_bytes(),Path(run['output']).read_bytes());checks+=1
    for step in reports['gates']['steps']:assert sha256(step['log'])==step['sha256']
    unit_tests=[sum(map(int,re.findall(r'test result: ok\. (\d+) passed;',Path(s['log']).read_text()))) for s in reports['gates']['steps'] if s['command'][:2]==['cargo','test']]
    rows=[];effects={}
    for case,results in batch['summary'].items():
        b=results['baseline'];c=results['candidate']
        effects[case]=dict(speedup=b['wall_seconds']['median']/c['wall_seconds']['median'],wall_reduction_percent=100*(1-c['wall_seconds']['median']/b['wall_seconds']['median']),rss_reduction_percent=100*(1-c['sampled_aggregate_rss_kib']['median']/b['sampled_aggregate_rss_kib']['median']))
        for label,values in results.items():
            w=values['wall_seconds'];rss=values['sampled_aggregate_rss_kib'];cpu=values['cpu_seconds']
            rows.append(f"| {case} | {label} | {w['median']:.3f} [{w['minimum']:.3f}, {w['maximum']:.3f}] | {cpu['median']:.3f} | {rss['median']/1024:.1f} |")
    tests=sum(v['passed'] for v in gate['backend_reports'].values())
    h=effects['human']
    result=f'''
## Accepted results: v0.3.2

The eight-site K64 transition-count kernel and exact-capacity message growth are
accepted together. Baseline v0.3.1 is preserved as `bin/psmc-rs-v0.3.1`; the accepted
binary is `bin/psmc-rs`, SHA256 `{candidate}`. The baseline source commit is
bdd1a4309502251f78ced5085f5d7aa498a200de. `bench/counts-build.json` records exact
source hashes, compiler, flags and linked libraries. Numerical changes, derivation,
isolated tests and measured evidence are committed together.

On the public HG001 chromosome 22 workload, the complete 30-bootstrap batch used
**{h['wall_reduction_percent']:.1f}% less wall time ({h['speedup']:.3f}x throughput)**
than the previous Rust release. Sampled peak RSS changed by
{(-h['rss_reduction_percent']):+.2f}%: this campaign does **not establish a resident-memory
benefit** from exact-capacity growth. Both releases use 16 workers, the same 30 seeds, 64 states and 30 EM
iterations. All fits and validation steps complete; no problematic seed is omitted.

| Workload | Release | Wall median [min,max], seconds | CPU median, seconds | RSS median, MiB |
|---|---|---:|---:|---:|
'''+ '\n'.join(rows)+f'''

These are one warmup plus three alternating measured pairs per workload on the
shared Intel Core i5-12600K host, using all 16 allowed logical CPUs. Wall time
includes scheduling and output. Peak RSS is sampled every 20 ms for human batches
and 10 ms for synthetic batches; it is a lower bound and excludes the controller.
K23 results are controls and do not imply a K64-kernel benefit at other state sizes.
Their measured wall medians were {(-effects['original']['wall_reduction_percent']):.1f}%
and {(-effects['model-based']['wall_reduction_percent']):.1f}% slower, respectively;
CPU medians changed little and ranges overlap. No K23 speedup is claimed.
A separate standard-Vec allocation diagnostic (`bench/counts-capacity.json`)
replays a 50,000-bin block followed by a 58,185-bin block. Per message buffer,
reported capacity changes from {reports['capacity']['rows'][1]['old_capacity_bytes']:,}
bytes under the old growth rule to {reports['capacity']['rows'][1]['new_capacity_bytes']:,}
bytes with exact reservation. This verifies tighter buffer capacity, not physical
RAM savings; untouched capacity need not appear in RSS. Successively increasing
record lengths can cause more reallocations than geometric growth.
Memory and kernel changes were measured as a combined release: the batch result
does not isolate their individual effects. Timing variability and three repeats
limit conclusions about small differences.

All **720 batch outputs** match retained pinned vanilla C numerical output exactly,
allowing only the honest version line. All 240 human outputs are finite. Original
synthetic batches retain their three pathological replicates and model-based
batches retain their one, exactly as C. Two additional complete unsplit chromosome
fits (baseline and candidate) also match C; their single-run times are correctness
controls, not repeated performance estimates. Bootstrap draws are independently
replayed and checked in every timed batch. The chromosome has 508,185 bins and
comes from the previously documented public smckit fixture; source provenance
and its limitations remain in `bench/hg-input.json` and the human-input report.
No human input is included in version control.

Acceptance checks: **{unit_tests[0]} debug and {unit_tests[1]} release unit tests**; **{tests} complete regression
cases** across dense, CPU/AVX and forced scalar, including ordered internal f64
snapshots; all **66 extended fixtures** ({reports['extended']['finite']} finite and
{reports['extended']['pathology_controls']} pathology controls); serial forward/reverse
30-bootstrap scheduler and cache controls; **{len(reports['review']['checks'])} CLI/dispatch
checks**. Lints completed with advisory style warnings. Whole-binary assembly
inspection found zero FMA and zero horizontal-reduction instructions. Runtime AVX
selection and non-AVX scalar fallback remain intact; absent-AVX behavior is simulated
in unit tests, not tested on a separate machine.

The isolated screen retained all four candidates and all 20 complete fit results.
Median seconds: baseline {reports['screen']['summary']['baseline']['wall_seconds']['median']:.3f},
memory only {reports['screen']['summary']['memory']['wall_seconds']['median']:.3f},
fixed K64 {reports['screen']['summary']['fixed64']['wall_seconds']['median']:.3f},
eight-site tile {reports['screen']['summary']['tile8']['wall_seconds']['median']:.3f},
32-site tile {reports['screen']['summary']['tile32']['wall_seconds']['median']:.3f}.
The eight-site candidate advanced based on the screen and then passed the complete
release gates above. Other kernels were not promoted. Single-fit screens allowed
OS scheduling across available CPUs; the matched full-batch measurements support
the release decision. The regenerated candidate source hashes match all saved
screen source hashes (`bench/counts-generator.json`).

### Reproduction and scope

Commands actually run are retained in `bench/counts-gates.json`,
`bench/counts-screen.json` and `bench/counts-batches.json`. Main entry points:

```
python3 bench/counts_campaign.py build
python3 bench/counts_campaign.py screen
python3 bench/counts_campaign.py verify_generator
python3 bench/counts_gates.py
python3 bench/counts_batches.py --candidate target/release/psmc-rs
python3 bench/counts_capacity.py
python3 bench/counts_report.py
```

Runners use fresh output directories and intentionally reject overwriting existing
raw evidence. The build/screen generator checks out the pinned baseline source;
its earlier build-runner hash predates screen/report plumbing repairs, while the
current generator is independently checked against every candidate source hash.
The final release build and gate runners have their own hashes. Historical C and
v0.3.1 reports are preserved unchanged. No C speed ratio is newly claimed here:
C output references are reused, but C timing was not repeated in this campaign.
The 10x goal remains unproven. ARM/NEON, GPU, whole genomes and the user's actual
workload remain untested. No approximation, changed model, FMA, altered optimizer
or additional HMM boundary is introduced.

Next permitted milestone: profile this accepted release on a whole-genome input
or a well-documented larger public workload before choosing further CPU work.
Per-fit reductions must remain ordered, and any next kernel must repeat the same
compatibility and complete-workload performance gates.
'''
    path=Path('docs/counts-optimization.md');text=path.read_text().split('\n## Accepted results:')[0];path.write_text(text+result)
    save('bench/counts-delivery-check.json',dict(status='passed',binary_sha256=candidate,source_matches_build=True,outputs_rechecked=checks,unit_tests=unit_tests,regression_cases=tests,effects=effects,reports={k:sha256(f'bench/counts-{k}.json') for k in names},report_sha256=sha256(path),runner_sha256=sha256(__file__)))
    print(json.dumps(dict(status='passed',outputs_rechecked=checks,effects=effects),indent=2))

if __name__=='__main__': main()
