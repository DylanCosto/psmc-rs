# Public human PSMC benchmark — 2026-10-10

On the full supplied NA12878 chromosome 22 test fixture, the retained Rust 0.3.1
release completed the matched 30-bootstrap batch **3.67x faster** than
already-parallel vanilla PSMC at 16 workers. All 30 bootstrap numerical outputs
match the pinned C reference exactly except the version line; 30/30 are finite.
The unsplit full-chromosome fit also matches exactly and is finite. No production
source or executable changed in this milestone.

The first verified Rust batch retained 9,000 block visits,
performed 5,880 message/count evaluations and reused
3,120 cached results. Every occurrence still contributes to the
fit. There were 3,584,539 model updates across the batch.

## Input and scope

The [upstream smckit quickstart](https://smckit.readthedocs.io/en/latest/get-started/quickstart-psmc.html)
identifies its bundled NA12878 chromosome 22 file as a real PSMC example. We used
[the pinned fixture](https://github.com/kevinkorfmann/smckit/blob/b5f0a200a99ecd86191780f0c8166d3e2ee0d776/src/smckit/data/examples/psmc/NA12878_chr22.psmcfa)
in full: 508,185 bins, with 356,491 T, 35,143 K and 116,551 N symbols.
At the standard 100-base PSMC encoding, this represents approximately 50.8 Mb.
The input SHA-256 is `0fe05d6fc19a94a3129803dc214660e0a72f2335ce5940b35fc3c9eab3698ea5`.

NA12878 is also designated HG001 in the [GIAB sample index](https://github.com/genome-in-a-bottle/giab_data_indexes). The preprocessed PSMC fixture itself comes from smckit.

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

| Implementation | Batch wall seconds | Aggregate CPU seconds | Sampled aggregate RSS KiB |
|---|---:|---:|---:|
| vanilla | 255.305 [252.131, 257.880] | 3513.239 [3478.464, 3532.759] | 970256.000 [970248.000, 970980.000] |
| rust | 69.616 [66.840, 70.179] | 910.919 [877.489, 912.878] | 1316596.000 [1316376.000, 1316656.000] |

Exploratory worker screens (one complete Rust batch each, not repeated medians):

| Workers | Wall seconds | CPU seconds | Sampled RSS KiB |
|---|---:|---:|---:|
| 8 | 79.213 | 550.587 | 776352 |
| 10 | 73.814 | 624.203 | 986108 |

The screens are insufficient to establish a universally best worker count or a
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

Diagnostic profiling covers the unsplit fit and bootstrap 01,
chosen for the highest total optimizer evaluation count, with lowest-index tie
breaking. Selection is only for attribution; all bootstraps remain in timing and
correctness results. The existing 0.3.1 diagnostic binary was reused after verifying
that its source exactly reconstructs current production code plus the recorded
timers. The timers measure thread CPU time. Instrumentation overhead is included;
these times do not support release speed claims.

| Exclusive section / diagnostic CPU seconds | Unsplit | Selected bootstrap |
|---|---:|---:|
| workspace_setup | 0.1532 | 0.0337 |
| forward | 3.2759 | 1.9801 |
| backward | 2.7275 | 1.8928 |
| likelihood_check | 0.0159 | 0.0096 |
| counts | 9.6309 | 5.8568 |
| prepare | 0.0007 | 0.0006 |
| model_update | 0.6020 | 0.6466 |
| q | 1.7105 | 1.8597 |
| normalizer | 0.0006 | 0.0006 |

| Inclusive diagnostic CPU seconds (overlapping scopes) | Unsplit | Selected bootstrap |
|---|---:|---:|
| expectation_inclusive | 15.8100 | 9.7846 |
| iteration_inclusive | 18.1620 | 12.3339 |
| fit_process_main | 18.1888 | 12.3413 |

unsplit: counts is the largest measured exclusive section (52.9% of diagnostic main CPU time); bootstrap-01: counts is the largest measured exclusive section (47.5% of diagnostic main CPU time).

Do not add inclusive totals to their child sections. Count accumulation, model
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
bin/psmc-rs bootstrap --backend cpu --workers 16 --replicates 30 \
  --memory-mib 4096 --seed 20261012 --output-dir work/hg-bootstrap-example \
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
