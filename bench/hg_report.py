#!/usr/bin/env python3
"""Validate retained human benchmark evidence and write the milestone report."""
import json
import os
from pathlib import Path
import statistics
from common import ROOT, save, sha256
from phase1_differential import compare_output
from phase2_common import source_hashes


def main():
    os.chdir(ROOT)
    names=['input','pilot','benchmark','profile']
    reports={n:json.loads(Path(f'bench/hg-{n}.json').read_text()) for n in names}
    assert all(r['status']=='passed' for r in reports.values())
    source=reports['input']; pilot=reports['pilot']; bench=reports['benchmark']; profile=reports['profile']
    assert bench['source_sha256']==profile['source_sha256']==source_hashes()
    assert sha256('bench/hg_benchmark.py')==bench['runner_sha256']
    assert sha256('bench/hg_profile.py')==profile['runner_sha256']
    assert sha256('bench/hg_prepare.py')==source['runner_sha256']
    assert sha256('bench/hg-input.json')==bench['input_manifest_sha256']
    for binary in bench['binaries'].values(): assert sha256(binary['path'])==binary['sha256']
    for item in source['sources']:assert sha256(item['path'])==item['sha256']
    assert sha256(source['blocks'])==source['blocks_sha256']
    for item in source['replicates']: assert sha256(item['path'])==item['sha256']
    assert all(not r['nonfinite_records_beyond_initial_RI'] for r in pilot['runs'])
    canonical=bench['canonical_outputs']; compared=0
    warnings=0
    for run in bench['runs']:
        assert run['all_30_exact']
        warnings += sum(p.read_text().count('Underflow') for p in Path(run['output_directory']).glob('child-*.stderr'))
        for expected, actual in zip(canonical,run['outputs']):
            assert sha256(actual['path'])==actual['sha256']
            compare_output(Path(expected['path']).read_bytes(),Path(actual['path']).read_bytes())
            if run['outputs']!=canonical:compared+=1
        if run['label']=='rust':assert run['draws_exact'] and run['actual_workers']==run['workers']
    assert len(bench['runs'])==10 and compared==270
    assert warnings==0, 'Record and investigate new underflow warnings before finalizing this report.'
    compare_output(Path(pilot['runs'][0]['output']).read_bytes(),Path(pilot['runs'][1]['output']).read_bytes())
    for case in profile['cases']:
        compare_output(Path(case['oracle']).read_bytes(),Path(case['run']['output']).read_bytes())
    for label,summary in bench['summary'].items():
        measured=[r for r in bench['runs'] if r['label']==label and r['kind']=='measurement']
        assert len(measured)==3
        for metric,expected in summary.items():
            vals=[r[metric] for r in measured]
            assert expected==dict(median=statistics.median(vals),minimum=min(vals),maximum=max(vals))
    first_rust=next(r for r in bench['runs'] if r['label']=='rust')
    statistics_files=sorted((Path(first_rust['output_directory'])/'fits').glob('replicate-*.stats.json'))
    stats=[json.loads(p.read_text()) for p in statistics_files]
    counters={k:sum(r[k] for r in stats) for k in ['sequence_visits','sequence_evaluations','cache_hits','model_updates']}
    assert len(stats)==30 and counters['sequence_evaluations']+counters['cache_hits']==counters['sequence_visits']
    finite=sum(not r['nonfinite'] for r in canonical)
    speed=bench['summary']['vanilla']['wall_seconds']['median']/bench['summary']['rust']['wall_seconds']['median']
    def fmt(values):return f"{values['median']:.3f} [{values['minimum']:.3f}, {values['maximum']:.3f}]"
    lines=['# Public human PSMC benchmark — 2026-10-10','',
        f"On the full supplied NA12878 chromosome 22 test fixture, the retained Rust 0.3.1\nrelease completed the matched 30-bootstrap batch **{speed:.2f}x faster** than\nalready-parallel vanilla PSMC at 16 workers. All 30 bootstrap numerical outputs\nmatch the pinned C reference exactly except the version line; {finite}/30 are finite.\nThe unsplit full-chromosome fit also matches exactly and is finite. No production\nsource or executable changed in this milestone.", '',
        f"""The first verified Rust batch retained {counters['sequence_visits']:,} block visits,
performed {counters['sequence_evaluations']:,} message/count evaluations and reused
{counters['cache_hits']:,} cached results. Every occurrence still contributes to the
fit. There were {counters['model_updates']:,} model updates across the batch.""", '',
        '## Input and scope','',
        f"The [upstream smckit quickstart](https://smckit.readthedocs.io/en/latest/get-started/quickstart-psmc.html)\nidentifies its bundled NA12878 chromosome 22 file as a real PSMC example. We used\n[the pinned fixture](https://github.com/kevinkorfmann/smckit/blob/{source['upstream_commit']}/src/smckit/data/examples/psmc/NA12878_chr22.psmcfa)\nin full: 508,185 bins, with 356,491 T, 35,143 K and 116,551 N symbols.\nAt the standard 100-base PSMC encoding, this represents approximately 50.8 Mb.\nThe input SHA-256 is `{source['input_sha256']}`.", '',
        '''NA12878 is also designated HG001 in the [GIAB sample index](https://github.com/genome-in-a-bottle/giab_data_indexes). The preprocessed PSMC fixture itself comes from smckit.

This is a chromosome test, not a whole-genome benchmark or a population-history
claim. Raw-read accession, reference assembly, caller and filtering for this
particular bundled file were not independently established. The upstream separate
prospective GRCh38 acquisition manifest is not used as its provenance. Encoded
missing bins are kept exactly; no absent VCF positions were converted to reference.
The upstream repository license is retained locally. Downloaded human input and
materialized samples stay under ignored work/hg-input and are not committed or
redistributed by this milestone.

Pinned original C splitfa splits the complete file into 50,000-bin blocks: nine
of that length and a final 58,185-bin block. Concatenating them exactly recovers the
original sequence. This explicit choice provides ten resampling blocks (about
5 Mb each at 100-base encoding); splitfa's 500,000-bin default would leave this
chromosome in one block. These are intended bootstrap boundaries, not computational
tiles inserted into the unsplit fit. The first two blocks are entirely missing;
they remain present and preserve their statistical contributions.

Thirty consecutive seeds 20261012–20261041 use the original ordered sampler and
nearest-length stopping rule. Sample lengths range from 500,000 to 524,555 bins.
All occurrences, including duplicate/all-missing blocks, remain in original draw
order. Exact per-expectation caching may share computation for identical bytes
while adding each occurrence separately. Source and materialized input hashes,
complete draw records, splitting command and all ten block summaries are in
`bench/hg-input.json`. No sample was selected or excluded based on outcome.

## Workload and measurements

Every timed run uses `-p '4+25*2+4+6' -N 30 -t 15 -r 5 -I 0`: 64 states and all
30 iterations. The [pinned lh3/psmc README](https://github.com/lh3/psmc/blob/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a/README)
human example uses this pattern with 25 iterations; we explicitly use 30 here. Rust uses CPU/auto AVX with its exact block cache.
Vanilla processes receive the identical pre-materialized bootstrap samples and
perform the same fits. The unmodified C executable uses no profiling instrumentation.

Host: Intel Core i5-12600K, 16 allowed logical CPUs, 10 physical cores, Linux/glibc.
All groups run sequentially at normal priority and inherit CPU IDs 0–15. No nested
numerical threading is introduced; each fit remains single-threaded. Rust requests
4096 MiB for memory admission so all 16 workers fit the conservative estimate.
This is an estimated admission budget, not a hard OS RSS limit.

The repeated 16-worker comparison uses one retained warmup and three measured
complete batches per implementation, alternating order between measured pairs.
The table shows median [minimum, maximum]. Wall time includes launch, resampling,
fitting and file output, but excludes post-run validation. CPU is summed child
user/system time. RSS is the maximum sampled sum of concurrently live child
processes at 20 ms intervals, excluding the controller; it is a lower bound on
true peak. Shared pages are counted in each C process's RSS, so this is not a
physical-memory/PSS comparison. Rust's workers share one process. This is a shared host.
''', '| Implementation | Batch wall seconds | Aggregate CPU seconds | Sampled aggregate RSS KiB |','|---|---:|---:|---:|']
    for label in ['vanilla','rust']:
        lines.append('| '+label+' | '+' | '.join(fmt(bench['summary'][label][key]) for key in ['wall_seconds','cpu_seconds','sampled_aggregate_rss_kib'])+' |')
    lines+=['','Exploratory worker screens (one complete Rust batch each, not repeated medians):','', '| Workers | Wall seconds | CPU seconds | Sampled RSS KiB |','|---|---:|---:|---:|']
    for run in bench['runs']:
        if run['kind']=='screen':lines.append(f"| {run['workers']} | {run['wall_seconds']:.3f} | {run['cpu_seconds']:.3f} | {run['sampled_aggregate_rss_kib']} |")
    lines+=['','''The screens are insufficient to establish a universally best worker count or a
small difference between configurations. Keep them separate from the fixed
16-worker repeated comparison. Full raw measurements, command arrays, host load,
worker admission and every output digest are in `bench/hg-benchmark.json`.

The unsplit pilot uses the same 64-state, 30-iteration options on the original
single record. Its first observed wall times were 58.222 s C and 18.151 s Rust;
peak RSS from /usr/bin/time was 539,796 and 515,876 KiB, respectively. These are
single-run measurements, not medians, and should not be compared directly with
bootstrap-batch wall time. See `bench/hg-pilot.json` for the exact commands.

## Exactness and diagnostic profile

The 30 C warmup outputs form the canonical references. Subsequent runs compare
270 output files against them (180 Rust fits and 90 repeated C controls). No
underflow warning was emitted in these batches. Draw
traces and manifests independently match all fixed bootstrap samples in every
Rust run. The unsplit Rust/C pair adds one output comparison. Two diagnostic
fits also match their respective C outputs. Only the honest version line is
excluded; all other numerical output and metadata bytes must match. Internal
state snapshots were not rerun for this unchanged production source; their prior
release evidence remains available. No tolerance was relaxed.
''', f"Diagnostic profiling covers the unsplit fit and bootstrap {profile['selected_bootstrap']:02d},\nchosen for the highest total optimizer evaluation count, with lowest-index tie\nbreaking. Selection is only for attribution; all bootstraps remain in timing and\ncorrectness results. The existing 0.3.1 diagnostic binary was reused after verifying\nthat its source exactly reconstructs current production code plus the recorded\ntimers. The timers measure thread CPU time. Instrumentation overhead is included;\nthese times do not support release speed claims.", '', '| Exclusive section / diagnostic CPU seconds | Unsplit | Selected bootstrap |','|---|---:|---:|']
    sections=['workspace_setup','forward','backward','likelihood_check','counts','prepare','model_update','q','normalizer']
    for name in sections:
        lines.append('| '+name+' | '+' | '.join(f"{case['profile']['sections'][name]['nanoseconds']/1e9:.4f}" for case in profile['cases'])+' |')
    lines+=['','| Inclusive diagnostic CPU seconds (overlapping scopes) | Unsplit | Selected bootstrap |','|---|---:|---:|']
    for name in ['expectation_inclusive','iteration_inclusive','fit_process_main']:
        lines.append('| '+name+' | '+' | '.join(f"{case['profile']['sections'][name]['nanoseconds']/1e9:.4f}" for case in profile['cases'])+' |')
    leaders=[]
    for case in profile['cases']:
        sections_by_name=case['profile']['sections']
        key=max(sections,key=lambda k:sections_by_name[k]['nanoseconds'])
        fraction=100*sections_by_name[key]['nanoseconds']/sections_by_name['fit_process_main']['nanoseconds']
        leaders.append(f"{case['name']}: {key} is the largest measured exclusive section ({fraction:.1f}% of diagnostic main CPU time)")
    lines+=['', '; '.join(leaders)+'.', '','''Do not add inclusive totals to their child sections. Count accumulation, model
updates, Q and message passes can now be prioritized from this human-input
profile. Residual expectation time includes hashing/cache lookup, aggregation,
observer and timer overhead. Hardware performance counters remain unavailable;
there is no claim of a precise cache-bandwidth diagnosis.

## Reproduction and delivery

Production source remains the accepted 0.3.1 implementation (numerical changes
in commit `7ee5271`; parallel evidence in `65d1d87`, delivery metadata in `b6fd847`).
The current executable SHA-256 is
`b0fc39d7c31637221de1152fc0d502bb65c90d0a5b9d6672250fe3117f75bfa4`.
Pinned vanilla source is `82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`, executable
`da1743512f1925da6277d5a2e5350c70c61c9771d11749df0918605f795ff32b`.
The compiler/toolchain and library stack remain those of the 0.3.1 build report.
Runners verify binary, input and source hashes before accepting results.

To run the tested human bootstrap workload from the repository root, use a new
output directory:

```sh
python3 bench/hg_prepare.py
bin/psmc-rs bootstrap --backend cpu --workers 16 --replicates 30 \\
  --memory-mib 4096 --seed 20261012 --output-dir work/hg-bootstrap-example \\
  -p '4+25*2+4+6' -N 30 -t 15 -r 5 -I 0 work/hg-input/blocks-50000.psmcfa
```

The executed benchmark entry points are:

```sh
python3 bench/hg_prepare.py
python3 bench/hg_benchmark.py --repeats 3
python3 bench/hg_profile.py
python3 bench/hg_report.py
```

Preparation downloads only the pinned public fixture and its license and requires
the existing pinned splitfa utility. The unsplit pilot was run before the batch
harness using common.timed_run; its full commands and /usr/bin/time measurements
are retained. The profile runner reuses the source-verified diagnostic build and
requires a fresh bench/hg/profile output directory and the local prior CPU campaign
scratch build, or its exact reconstruction
using cpu_campaign_final_profile.py's recorded instrumentation. Raw outputs stay
under bench/hg; no archive from a prior milestone is replaced.

This milestone changes benchmark runners, provenance, measurements, EXECPLAN and
this report. Production crates stay unchanged. Remaining limits are actual user
input/settings, whole-genome memory/scaling, independently reproduced raw-data
preprocessing, larger human cohorts and other hardware. No 10x or whole-genome
speed claim follows from this chromosome test.

The next permitted optimization milestone should target the largest measured
exclusive section above and measure workspace allocation capacity to explain the
higher Rust batch RSS. Any candidate must preserve ordered f64 operations and all
counts, pass this exact human-output gate plus the existing synthetic/internal
gates, and improve repeated complete-batch timings. A one-run worker screen or
small kernel speedup is insufficient to change the release.
''']
    Path('docs/hg-benchmark-report.md').write_text('\n'.join(lines))
    save('bench/hg-delivery-check.json',dict(status='passed',source_unchanged=True,underflow_warnings=warnings,counters=counters,report_sha256={n:sha256(f'bench/hg-{n}.json') for n in names},human_report_sha256=sha256('docs/hg-benchmark-report.md'),timed_bootstrap_outputs=300,canonical_c_bootstraps=30,subsequent_exact_comparisons=compared,finite_bootstraps=finite,unsplit_exact=True,diagnostic_comparisons=2,runner_sha256=sha256(__file__)))
    print(f'Human-input report and audit complete: {speed:.3f}x matched batch speedup; {finite}/30 finite bootstraps.')

if __name__=='__main__': main()
