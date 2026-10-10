# Phase 2: strict CPU optimization and deterministic bootstraps

The first optimization milestone is complete on the pinned Linux stack. The
optimized CPU backend passes its exact compatibility gate and improves complete
synthetic fits by **1.51–1.59× over the previous Rust release** and **1.14–1.26×
over vanilla PSMC**. The 30-fit synthetic bootstrap batch runs **1.48–1.52× faster
than vanilla at equal worker counts**. That batch includes three known original
PSMC nonfinite trajectories and measures execution mechanics, not validated
production inference. The 10× target and the user's real workload remain unproven.

Select `--backend cpu` to use the optimization. The default remains the retained
`dense` oracle. No numerical tolerance, model, precision, optimizer, iteration
count, sequence boundary or full-count objective was changed. No CUDA or Phase 3
structured-algebra implementation is included.

## Delivered changes

| Files | Result |
|---|---|
| `crates/psmc-cpu/{Cargo.toml,src/lib.rs,src/engine.rs,src/tests.rs}` | New prepared model, reusable forward/backward/count buffers and exact repeated-record cache |
| `crates/psmc-core/src/{model_workspace.rs,em.rs,lib.rs}` | Reusable model scratch and backend interface; ordered EM aggregation retained |
| `crates/psmc-io/src/lib.rs` | Ordered bootstrap indices let fits share encoded observations |
| `crates/psmc-cli/src/{main.rs,batch.rs,legacy.rs,snapshot.rs}` | Explicit backend/cache/stats options, bounded independent-fit queue, deterministic seeds, manifests and nonfinite-output diagnostics |
| Root Cargo files | Version 0.2.0, four local crates, no registry dependencies |
| `bench/phase2*`, `bench/phase-2-*`, CPU examples | Exact comparison, scheduling, review, negative controls, isolated and integrated measurements |
| README, contracts, execution plan and Phase 2 documents | Usage, derivations, acceptance evidence and limitations |

The literal dense `hmm.rs`, `model.rs` and `optimizer.rs` files are byte-identical
to Phase 1. [Source verification](../bench/phase-2-source-audit.json) checks both
the saved source and the historical build hashes. The
[engineering note](phase-2-engineering.md) derives every storage/cache change and
links isolated tests and timings. Model workspaces retain six scratch vectors;
HMM workspaces retain flat buffers and prepare matrix products once per immutable
model. Cache entries exist only within one expectation call, keyed by complete
encoded bytes. Every occurrence still contributes in its original order,
including its per-record tiny counts. Snapshots explicitly bypass count caching
when the CPU backend is selected, so all messages remain visible.

The bootstrap queue parallelizes complete independent fits. Each replicate owns
its RNG and numerical workspace; only input observations are shared. There is
no nested pool or parallel floating-point reduction. Replicate i uses base seed
plus i, consumes the original sampling draws, then continues the same RNG stream
for parameter initialization. The memory estimate controls admission and includes
retained manifest metadata; it is not an OS-enforced RSS ceiling, and input is
loaded before admission.

## Exactness and review

The final executable passes **226 inherited differential controls**, 113 for each
backend, against the pinned normal/instrumented C reference. These include all
30 full K23/N30 materialized bootstrap trajectories per backend, supported options,
input/output handling and selected complete internal traces. Only the single
honest `MM Version` record is excluded from output byte comparisons.
[Validation results](../bench/phase-2-validation.json).

Six complete snapshot comparisons (three per backend) cover **15,086 ordered
events and 4,371,374 finite numeric fields**, with zero mismatches. Finite binary64
values and signed zero compare exactly; nonfinite classes are checked separately.
No snapshot event was truncated. The two largest unchanged Phase 1 diagnostics
are retained rather than rerun; the [protocol](phase-2-validation-protocol.md)
names them and explains the bounded scope. K64 full outputs and isolated CPU
messages/counts are rechecked.

The isolated HMM tests include all 3,279 observation strings of lengths 1–7 and
240 model configurations across 1/2/4/23/64 states. Model-workspace tests compare
64,446 values exactly with dense Rust and retained C, with additional poisoned
scratch and invalid-to-valid recovery controls. All **27 unit tests pass in both
debug and release**, and formatting passes. [Build checks](../bench/phase-2-cargo-checks.json),
[model results](../bench/phase-2-model-workspace/results.json).

All **180 full scheduler fits** (30 replicates × workers 1/2/4 × forward/reverse
job order) reproduce original outputs and ordered samples. Cache-on, cache-off
and full-message snapshot controls agree. Three further randomized-initialization
bootstrap comparisons verify RNG consumption after resampling.
[Scheduler results](../bench/phase-2-scheduler.json).

Across one 30-fit batch, 11,730 sequence visits require 7,740 evaluations and
3,990 cache hits: **34.02% of repeated evaluations avoided**. Every visit still
contributes statistically. One diagnostic replicate has 13 occurrences and eight
unique strings: cache on evaluates eight; off and snapshot modes evaluate all 13.
No parameter-derived cache survives an expectation call.

All **17 independent CLI/scheduler review controls pass**. Review found and fixed
an all-missing-input case that could truncate output before validation, and an
underestimate of retained batch metadata. Earlier evidence remains labeled as
corrected. Single-fit validation now precedes opening output/snapshot/trace files;
nonfinite diagnostics now include RI-only printed failures.
[Review](phase-2-review.md), [results](../bench/phase2-review.json).

Reference pathologies remain explicit: bootstrap indices 16, 26 and 28 first
produce nonfinite printed records at QD28, LK26 and RI23 respectively. The other
27 trajectories are finite. Matching these three pathologies is an output
compatibility result, not scientific validation. Nonfinite optimizer trials are
also preserved. No new regularizer or changed optimizer hides the original behavior.

## Complete-fit measurements

Measurements ran after builds, tests and profiling finished. Each implementation
received one warmup and five measured runs, rotating execution order. Every output
was compared; binaries and inputs were hash-guarded. Wall time includes startup,
parsing and output. K23 uses 13,200 bins and 30 iterations. K64 uses 52,800 bins
and five iterations; it is a finite partial trajectory, not a complete production
fit. Both fixtures have three genuine sequence records.

| Case | Vanilla C | Phase 1 Rust | Current dense | Optimized CPU | Speed vs Phase 1 | Speed vs C |
|---|---:|---:|---:|---:|---:|---:|
| K23 / N30 | 0.385 s | 0.486 s | 0.493 s | 0.306 s | 1.589× | 1.256× |
| K64 / N5 | 1.581 s | 2.106 s | 2.054 s | 1.391 s | 1.514× | 1.136× |

Median per-process maximum resident memory, measured by Linux `/usr/bin/time`:

| Case | Vanilla C | Phase 1 Rust | Current dense | Optimized CPU |
|---|---:|---:|---:|---:|
| K23 / N30 | 4,680 KiB | 5,076 KiB | 5,164 KiB | 5,188 KiB |
| K64 / N5 | 27,308 KiB | 26,556 KiB | 26,664 KiB | 26,772 KiB |

Buffer reuse reduces allocation work; it does not produce a substantial peak-RSS
reduction on these small records. Full forward/backward storage is still retained.
[Raw runs, ranges, hashes and medians](../bench/phase-2-benchmark.json).

## Equal-worker bootstrap measurements

These runs use all 30 original-length, 30-iteration synthetic replicates, including
the three retained pathologies. Each worker count has one warmup and three measured
batches per implementation. C receives pre-materialized inputs; Rust also resamples
from source blocks during its timed command. Both write legacy output. Rust
additionally writes per-fit counters, draw traces and a manifest; batch phase
profiling is disabled. The same worker budget is used on both sides.

| Workers on each side | Vanilla processes | Rust CPU queue | C / Rust wall ratio |
|---|---:|---:|---:|
| 1 | 12.027 s | 8.132 s | 1.479× |
| 2 | 6.088 s | 4.003 s | 1.521× |
| 4 | 3.124 s | 2.081 s | 1.501× |

Ordinary concurrency is separate: 1-to-4-worker throughput improves 3.850× for C
and 3.907× for Rust on this synthetic batch. The relevant acceleration over the
user's already-parallel workflow is the **equal-worker** comparison above, not
C serial time divided by Rust parallel time.

A 10 ms child-tree sampler records median observed aggregate RSS below. It
includes process-launch transients and `/usr/bin/time`, double-counts shared
resident pages across processes, and excludes the Python parent harness. It is
a sampled lower bound on instantaneous child-tree RSS, not allocator memory or
an isolated inference-memory ratio.

| Workers | C sampled child-tree RSS | Rust sampled child-tree RSS | Rust process maximum RSS |
|---|---:|---:|---:|
| 1 | 31,756 KiB | 5,688 KiB | 3,844 KiB |
| 2 | 9,084 KiB | 6,556 KiB | 4,656 KiB |
| 4 | 17,964 KiB | 8,416 KiB | 6,384 KiB |

The anomalous C one-worker sampled peak illustrates why these sampled numbers
must not be advertised as inference-memory savings. Raw per-child maximum RSS
and sampling counts are retained. There is no exact aggregate maximum-RSS value
for the C batch; the report leaves that field null.

All 48 serial commands and 24 timed/warmup batches have exact outputs. A separate
[post-run audit](../bench/phase-2-benchmark-audit.json) confirms all 360 C child
exits are zero and all 12 Rust manifests admitted exactly their requested workers.
Read-only harness review identified checks worth making explicit for future runs:
actual admitted workers, negative signal exits and conflicting selection flags.
The immutable measured runner and report are preserved. The audit establishes
that these latent harness issues did not affect this invocation; the reproducer
now passes all nine harness regression controls. [Harness results](../bench/phase-2-harness-selftest.json). No output mismatch or failed inference
process was dropped from the timing set.

## Remaining bottleneck and isolated timings

The isolated HMM benchmark improves by 2.111× at K23 and 1.727× at K64 versus the
dense Rust HMM. Model scratch reuse improves K23 model updates by 1.135× and is
essentially neutral at K64 (1.008×). An allocation probe sees 6,000 dense versus
zero workspace scratch allocations over 1,000 K64 updates. These are isolated
measurements; they do not replace the complete-fit results. The initial slower
model-workspace attempt and a kernel-build provenance caveat are retained in the
[engineering note](phase-2-engineering.md) and owning reports.

Separate one-run E/M timing diagnostics, outside the benchmark window:

| Case / backend | Expectation section | M-step section |
|---|---:|---:|
| K23 / dense | 0.334 s | 0.165 s |
| K23 / CPU | 0.158 s | 0.148 s |
| K64 / dense | 1.430 s | 0.628 s |
| K64 / CPU | 0.778 s | 0.615 s |

The M-step is about 48% and 44% of these timed CPU sections. This is a coarse
instrumented diagnostic, not repeated benchmark evidence or attribution to one
optimizer function. It explains why faster HMM kernels alone do not deliver a
10× full-run result. [Diagnostic report and commands](../bench/phase-2-profile.json).
The next permitted milestone is Phase 3: derive and validate structured CPU
operations while retaining full legacy counts, the normalizer and dense objective
oracle; then profile again. GPU promotion remains a later, independently gated
step. No Phase 3 numerical transformation has been promoted by this report.

## Reproduction, provenance and untested scope

The reference source is `82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`, built with the
recorded GCC 13.3/O2/no-contraction configuration. Rust uses 1.90.0, release
opt-level 2, one codegen unit, no LTO and no fast-math or target-specific flags.
The host is an Intel i5-12600K with 16 visible logical CPUs, x86-64 Linux Mint
22.3/glibc 2.39. The shared host was not CPU-isolated or governor-controlled.
System/library digests and all Cargo manifests/source hashes are in
[the build record](../bench/phase-2-build.json).

| Executable | SHA-256 |
|---|---|
| Delivered `bin/psmc-rs` 0.2 | `fd866573a007003d2388137270ec24f14acb436c42c7084ab8dac076fdabb59a` |
| Preserved Phase 1 Rust | `e112ed9a8d7d98cc5e29f497e8567e1de96f3e0210a0cb324a79dc91c5e65dd0` |
| Vanilla C | `da1743512f1925da6277d5a2e5350c70c61c9771d11749df0918605f795ff32b` |
| Instrumented C, correctness only | `2b4bd7dd369ee8fc226270b30bd414a031314fd70445bd5d7a83d4e5d2f2ed55` |

Actual commands, arguments, return codes and raw-file hashes are recorded in the
linked reports. The [README reproduction sequence](../README.md#reproduce-this-milestone)
contains the commands used for build, debug/release tests, final validation,
scheduler gate, review, negative controls, uninstrumented timings and separate
profiling. Isolated reproductions are linked in the engineering note. Final
correctness and timings use frozen executable copies; no rebuild occurred during
measurement. Earlier validation runs are retained but excluded from final counts.

The compact [package description](../PACKAGING.md) identifies source, executable,
synthetic inputs, reports and explicit snapshot omissions. Full compared snapshots
remain local with exact hashes and reproduction commands. Source, derivations,
tests and measurements are saved together. Earlier Phase 0/1 archives remain intact.

Real input and splitting/callability provenance, exact production flags and worker
budget, full-genome memory behavior, cross-platform bitwise compatibility, other
CPUs, CUDA, hard memory exhaustion, disk exhaustion, termination recovery and
checkpoint/resume are **not_run**. Phase 1 tested legacy conversion/data scripts;
this milestone's byte-exact output gate retains that format, but plotting/rendering
was not rerun. No private genome or cohort was accessed. This is a completed local
CPU engineering gate, not completion of the full production/GPU release plan.
