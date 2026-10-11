# v0.6.3 memory safety and 200 Mb qualification

The prospective 200 Mb panel passed all declared primary-band and event checks.
All 30 strict fits matched pinned vanilla C exactly, except the version line.
The release also limits strict single-fit concurrency by estimated memory rather
than automatically keeping a chromosome history on every available worker.
Equivalent remains opt-in. This is evidence for the tested synthetic histories,
not whole-genome or universal scientific qualification.

## Frozen design and provenance

Source commit: `35b26e417eaae752d65cefcc4948ea03adecc8b9`, clean at panel launch.
The [protocol](known-truth-200mb-protocol.md) was committed before generating data;
its SHA-256 is `25acc1e7700b25faa6b709ea882d2dde94a2bc315f8d8582e6ad1137b4fa77e1`.
Installed v0.6.3 and the frozen panel executable share SHA-256
`682be008483ef60aa226e448f03d2f1f073b008a87787f9fe7af78fe9bd810fb`.
The [full results](../bench/known-truth-200mb-results.json) preserve all seeds,
commands, inputs' hashes, binary hashes, PA parameters, curves and per-fit metrics.
The [audit](../bench/known-truth-200mb-audit.json) verifies all 30 inputs and 90 fits,
physical simulation units/events, hashes, strict/C equality and metric summaries.

Ten datasets per history, each twenty independent 10 Mb sequences (200 Mb), were
simulated with pinned Hudson ms. Mutation rate 2.5e-8 and recombination rate 5e-9
per base per generation; 100-base bins. All three engines used 64 states,
`-p 4+25*2+4+6 -N 30 -t 15 -r 5 -I 0`, alpha 0.1, one record worker.
There were no failed or excluded simulations/fits. The constant history has Ne
10,000; the bottleneck has Ne 2,000 during 10k–30k generations; the expansion has
Ne 20,000 during 0–20k and 10,000 earlier.

Pinned PSMC source is `82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`.
The ms archive/build provenance remains in
[the source record](../bench/known-truth-provenance.json). Tested on i5-12600K,
x86-64 Linux, glibc 2.39, GCC 13.3.0 and Rust 1.90.0. Eight independent fits ran
concurrently. During the first wave, the harness and its children were restricted
to allowed P-core threads to avoid slow-core control timeouts; the exact
[resource adjustment](../bench/known-truth-200mb-resources.json) is retained.
No data, fitting options, binaries, cases or gates changed. Recorded wall times
are diagnostics under shared load; **no performance claim** follows from this panel.

## Primary accuracy results

Values are natural-log Ne errors. Truth error is the mean of ten per-dataset
RMSEs; mode difference is pooled RMS across those datasets and each band's 128
log-spaced time points. C and strict truth errors are identical.

| History | Generations | Strict truth RMSE | Equivalent truth RMSE | Pooled mode difference | Upper paired error bound |
|---|---|---:|---:|---:|---:|
| constant | 5k–20k | 0.068804 | 0.068804 | 7.97e-06 | 1.43e-06 |
| constant | 20k–80k | 0.046232 | 0.046232 | 3.36e-06 | 7.09e-07 |
| bottleneck | 5k–20k | 0.380672 | 0.380672 | 7.69e-06 | 9.53e-07 |
| bottleneck | 20k–80k | 0.442846 | 0.442845 | 2.28e-05 | 3.59e-06 |
| expansion | 5k–20k | 0.159355 | 0.159355 | 7.98e-06 | 1.55e-06 |
| expansion | 20k–80k | 0.059955 | 0.059956 | 3.12e-06 | 1.41e-06 |

All six primary comparisons pass: the one-sided 95% paired mean-error bound is
below 0.05, pooled mode difference is below 10% of strict truth error, and each
mode's mean truth RMSE is at most 0.5. The largest observed mode-difference fraction
is about 0.0107% of strict truth error. These are the fixed descriptive budgets,
not universal scientific accuracy thresholds; the paired bounds are not a
simultaneous confidence statement across all six comparisons.

Median bottleneck Ne ratio was **0.180911 strict / 0.180912 equivalent**, versus
truth 0.2 (required <0.75). Median expansion ratio was **1.933346 / 1.933348**,
versus truth 2 (required >1.25). Both modes recover the prespecified event direction.
Bottleneck mean errors remain larger than the other histories, so mode agreement
does not imply exact reconstruction of an abrupt demographic event.

## Diagnostic windows and outliers

These windows were retained prospectively but were not acceptance gates:

| History | Generations | Strict truth RMSE | Equivalent truth RMSE | Pooled mode difference |
|---|---|---:|---:|---:|
| constant | 1k–5k | 0.306082 | 0.306084 | 1.89e-05 |
| constant | 80k–200k | 0.114011 | 0.114009 | 8.85e-06 |
| bottleneck | 1k–5k | 0.219210 | 0.219207 | 2.59e-05 |
| bottleneck | 80k–200k | 0.178796 | 0.178792 | 1.7e-05 |
| expansion | 1k–5k | 0.246664 | 0.246663 | 2.29e-05 |
| expansion | 80k–200k | 0.081165 | 0.081160 | 1.52e-05 |

No dataset exceeded the prespecified 0.01 mode-to-mode RMSE trigger in any band.
Consequently the conditional fresh-likelihood/common-Q/ridge diagnostic was not
run for this panel. This does not resolve the geometry of the earlier pilot's
four outliers. Their historical results and gates remain intact; the user's
post-hoc time-band analysis is reproduced in
[the pilot amendment](qualification-report.md#follow-up-the-pilots-time-dependence).

Thirty additional equivalent fits collected fallback counters. Every instrumented
replay exactly matched its original uninstrumented output; **zero structured
fallbacks in 3,634,535 model updates**. The
[per-case counters](../bench/known-truth-200mb-stats.json) are retained. These
replays are diagnostic, separate from the 90 primary fits, with no timing claim.

## Strict memory regression

Default strict CPU admission uses half detected available memory, including
cgroup headroom where exposed; `--memory-mib` supplies an explicit budget. The
largest record's history is reserved per worker, plus retained owner/decoder
histories, observation copies, counts and overhead. If one worker cannot fit, the
command rejects before opening result files. Input parsing precedes admission,
and this estimate is not an OS-enforced memory limit. Independent processes need
separate budgets. See [policy and allocation tests](strict-memory-admission.md).

Eight distinct 1M-bin records reproduced v0.6.2 serial output with requested 16
workers capped to one at 2048 MiB (995 MiB measured RSS) and two at 3500 MiB
(about 1988 MiB RSS). A separate full 30-iteration fit on the 200 Mb constant-00
input admitted **three workers at 512 MiB**, estimated 441 MiB, and peaked at
**304 MiB RSS**. Its complete output was byte-identical to the serial strict fit.
[Full-fit memory evidence](../bench/strict-memory-full-fit.json) includes exact
bytes and hashes. These are memory/order checks, not a new speed benchmark.

## Validation and reproduction

59 Rust release tests passed; four CUDA hardware tests were ignored/not_run.
Six Python converter/scaling/grid tests and four live pinned-C golden checks
passed. All-feature compilation, Rust formatting and diff checks passed.
Memory changes affect admission/CLI/batch estimator reuse only; no inference
kernel, optimizer, precision or sequence boundary changed. The CI workflow now
includes both known-truth test modules, but hosted CI is not_run without a remote.

Commands run from the repository (raw logs and genomes stay in ignored `work/`):

```bash
cargo test --release --locked --offline --workspace
cargo check --release --locked --offline --workspace --all-features
cargo fmt --all -- --check
python3 -m unittest discover -s bench -p 'test_known_truth*.py'
python3 bench/ci_strict_reference.py --reference work/vanilla/psmc
python3 bench/strict_memory.py --output work/qualification/memory-rss-final
python3 bench/known_truth_200mb.py --output work/qualification-200mb/panel --jobs 8
python3 bench/audit_known_truth_200mb.py --panel work/qualification-200mb/panel
python3 bench/known_truth_200mb_stats.py --panel work/qualification-200mb/panel
```

Panel and memory runner destinations must be new when reproducing; use a new
output directory rather than replacing the retained evidence.

## Remaining scope

This is 200 Mb of idealized, independent sequence per dataset, not a human-sized
genome. Whole-genome chromosome lengths/dependence, real callable masks, errors,
structure, selection, other demographic histories, ARM/non-Linux execution and
CUDA hardware are unqualified here. The next scientific milestone is a separately
prespecified genome-scale panel and the user's actual input, splitting procedure,
mask and command. Hosted CI needs the remote repository URL. Neither missing
external input was substituted or marked passed.
