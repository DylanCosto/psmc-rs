# CPU defaults and first known-truth qualification

The main drive has about **24 GiB free**, up from about 5 GiB. Historical evidence
has been moved to the external backup drive and verified, and the rebuildable
debug cache was removed. See [archive inventory](../bench/evidence-archive.json)
and [restoration guide](evidence-archive.md). All 87 archives preserve 90,993
file/link entries; their compressed size is 13,681,890,583 bytes. No source code
or scientific evidence was discarded.

## Release scope

Version 0.6.2 fixes CPU classification and changes the default record-worker
policy. Linux `/sys/devices/cpu_core/cpus` and `/sys/devices/cpu_atom/cpus` take
precedence when disjoint and complete for the inherited affinity mask. Frequency
fallback accepts cores at >=85% of the maximum. Unknown topology stays unpinned.
E-core-only affinity still admits fit owners. Tests cover preferred boost cores,
missing frequencies, malformed/overlapping/incomplete lists and restricted CPUs.

Ordinary single CPU fits now default to the available CPU count. Explicit worker
limits remain supported. Dense, CUDA, snapshots and bootstrap retain their
separate worker policies. Strict per-record histories can raise memory use;
single fits have no memory-admission budget. The README now leads with usage,
mode guarantees, resource controls and limits. Strict remains the default;
equivalent remains experimental and opt-in. No inference arithmetic changed.

The source baseline is `b12cc90`; this report and the source changes are committed
together. The pilot ran the final inference/CLI implementation before the
version-only change to 0.6.2. Frozen and installed binary hashes, final default
checks and memory/timing screens are in
[qualification-install.json](../bench/qualification-install.json).

## Known-truth pilot

The [prospective protocol](known-truth-protocol.md) was frozen before simulation,
SHA-256 `b7f55bac1a78e0c1d987be3080af6c9eb62deae9f0983f6c40b8049170c21fc2`.
It uses [Hudson's author-distributed ms source](https://home.uchicago.edu/rhudson1/source/mksamples.html),
compiled unmodified with GCC 13.3.0, and pinned PSMC's `history2ms.pl` for parameters.
The adapter changes the executable and output switch from msHOT-lite to standard
ms, retains demographic/mutation/recombination arguments, and uses 12-decimal
positions and explicit three-word seeds. The standard ms converter checks both
haplotypes and exact bin boundaries; it does not use the incompatible upstream
msHOT-lite output parser.

There are ten independent datasets for each of constant, bottleneck and expansion
histories: **30 datasets, 90 full fits**, with vanilla C, strict and equivalent.
Each dataset contains twenty independent 1 Mb sequences, encoded into 100-base
bins. Every fit uses 64 states, 30 EM iterations, max time 15, theta/rho ratio 5
and no random initialization. The mutation and recombination rates are fixed and
known. There are no masks or sequencing errors. Curves are scaled into population
size and generations using each fit's theta, without post-fit alignment.

Mean root mean square natural-log population-size error, on the prespecified
256-point log-time grid from 1,000 to 200,000 generations:

| History | Vanilla C / strict | Equivalent | Upper 95% paired mean error difference | Pooled mode difference / strict truth error |
|---|---:|---:|---:|---:|
| Constant | 0.571404 | 0.571395 | 0.00000724 | 0.00659% |
| Bottleneck | 0.943506 | 0.942246 | 0.001479 | 4.11% |
| Expansion | 1.013587 | 0.995148 | 0.015224 | 4.18% |

All 30 strict outputs match vanilla C exactly except the version line. All final
parameter vectors are finite. Both prespecified relative-mode budgets pass in
all histories: upper paired difference <0.05 log units, pooled mode difference
<=10% of strict's error against truth. The paired t interval has only ten
replicates and assumes approximate normality; it is pilot evidence.

**Absolute recovery is often poor in both modes on this panel.** Individual
strict RMSE reaches 3.684 for expansion replicate 9. Passing the relative-mode
budgets says equivalent did not materially worsen recovery under this particular
assessment; it does not say either curve reliably recovered truth. The short
20 Mb datasets, independent 1 Mb records and broad time grid limit this pilot's
relevance to an actual whole-genome workflow. No cases were excluded or thresholds
changed after seeing results. All curves, parameters, seeds, commands and errors
are in [known-truth-results.json](../bench/known-truth-results.json).

## Outlier diagnostics and remaining numerical limits

Post-hoc inspection selected four cases with mode-to-mode curve RMSE >0.01.
Fresh endpoint likelihoods and Q on each endpoint's *same* expected counts were
recomputed using the retained strict CPU engine. This is diagnostic, not another
passing threshold or a profile-likelihood analysis.

| Case | Mode curve RMSE | Fresh LL difference (equivalent − strict) | Largest absolute common-count Q difference |
|---|---:|---:|---:|
| Bottleneck 1 | 0.07394 | 0.002100 | 0.03718 |
| Bottleneck 3 | 0.12579 | 0.000779 | 0.004824 |
| Bottleneck 9 | 0.03043 | −0.000614 | 0.01805 |
| Expansion 9 | 0.18620 | 0.004177 | 0.04685 |

Three cases have first-group lambda around a million or larger, but a universal
flat-ridge explanation is **not established**. In particular, all four common-Q
differences exceed the earlier HG-panel diagnostic budget of 1e-8 per bin
(the range here is 2.41e-8 to 2.34e-7). That earlier budget was not the prospective
truth-pilot gate; its failure to generalize is still relevant and is retained
explicitly. Do not present this pilot as satisfying every previous numerical gate
or as full scientific qualification. Lambda0-only slices and endpoints are in
[known-truth-ridge.json](../bench/known-truth-ridge.json).

## Verification and reproduction

- 55 release Rust tests passed; four CUDA hardware tests ignored/not_run.
- Four Python conversion/scaling tests passed.
- Four live pinned-C golden cases matched exactly.
- 32 complete bootstrap outputs matched within each mode across all-core,
  P-core-only, E-core-only and mixed affinity masks on this i5-12600K.
- Six final installed-release full fits using automatic workers matched frozen
  serial fits, excluding the version line: replicate 9 of each simulated history,
  in both modes. Tests also cover repeated records with cache on and off.
- Release all-feature compilation, formatting and diff checks passed. The
  [audit](../bench/qualification-audit.json) confirms the inference core, CPU
  engines and input code are unchanged from b12cc90.

Commands used, from the repository root:

```bash
cargo test --workspace --release --locked --offline
cargo check --workspace --release --all-features --locked --offline
cargo fmt --all -- --check
python3 -m unittest discover -s bench -p test_known_truth.py
python3 bench/ci_strict_reference.py --reference work/vanilla/psmc
python3 bench/topology_defaults.py --output work/new-topology-check
python3 bench/known_truth.py --ms work/qualification/msdir/ms \
  --reference work/vanilla/psmc --output work/qualification/panel --jobs 4
```

For a new run, build the pinned C reference using README_PHASE0.md, and fetch/build
ms with `python3 bench/prepare_ms.py --output work/ms-reference` (new directory).
Use that ms executable and a new panel output directory. The runner refuses to
overwrite a panel. [Provenance](../bench/known-truth-provenance.json) records
source/archive/compiler hashes; raw current results remain in `work/qualification`.
Qualification was suspended while disk cleanup took priority. Its raw durations
include that pause and are **not performance evidence**. No new speedup claim is
made; the historical v0.6.1 timing evidence remains in its archived reports.

Hosted CI is **not_run**: no remote is configured and the requested repository URL
has not been supplied. The workflow is ready and now includes converter/scaling
tests. Actual-user-workload qualification is **not_run**: input, splitting/mask
provenance and command are still missing. GPU, other CPU families, ARM and
non-Linux hardware were not qualified in this milestone.

Next work is larger/realistic qualification and investigation of the numerical
outliers, not another performance campaign. Keep the current scientific limits
visible until those tests are available.
