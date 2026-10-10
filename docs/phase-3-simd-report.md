# Phase 3a: strict single-thread SIMD

Rust 0.3 adds a validated, runtime-dispatched AVX path for independent HMM state
and count lanes. The dense oracle and generic CPU path remain available. All
builds, numerical tests and measurements ran with one allowed CPU, one Cargo job,
one Rust test thread and reduced scheduling priority. No parallel bootstrap or
multi-agent work was used for this milestone.

On these synthetic fits, median child CPU-time ratios improve **1.12× at 23
states and 1.31× at 64 states versus the preserved Phase 2 CPU executable**. The
serial 30-bootstrap batch shows **no clear additional improvement** over Phase 2:
its CPU-time ratio is 1.005× with substantial overlapping variation, and its
median wall time is slower. SIMD therefore passes the correctness gate and helps
the measured unsplit fits; it does not establish another bootstrap throughput
gain, production performance, or the project's 10× target.

Use `--backend cpu --simd auto` (auto is the default for CPU) to select AVX when
supported. `--simd off` retains the generic CPU calculation. The overall backend
default remains dense. `bin/psmc-rs-phase2` preserves the exact previous executable;
no old archive or evidence was replaced.

## Implementation and derivation

The numerical source baseline is local commit
`374de5a520adbefa646e182bd70702d1ef681326` (Phase 2). The pinned external C source
remains `82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`. The new implementation consists of:

- `crates/psmc-cpu/src/simd.rs`: private runtime-detected AVX capability, checked
  slice wrappers and three isolated intrinsic functions for forward, backward and
  full transition counts. Explicit SIMD modes are auto/off/avx.
- `crates/psmc-cpu/src/lib.rs`: per-workspace selection, copied backward product
  transpose, original scalar fallback, and ordered forward normalization.
- `crates/psmc-cpu/src/engine.rs`: per-fit selection and preparation integration;
  duplicate caching and occurrence-order aggregation retain their previous rules.
- CLI options/stats: explicit SIMD selection, pre-output rejection of invalid
  requests, and `simd_requested`/`simd_selected` metadata. The version becomes 0.3.0.
- Isolated tests, SIMD benchmark example, one-CPU build/gate/measurement scripts,
  derivation, report and updated use instructions.

Each vector contains four independent binary64 destinations. Every lane receives
the original multiply/add sequence in source order; forward normalization remains
an ascending scalar sum. Count lanes receive the same per-site addends, including
initializers and the final-site emission omission. There is no horizontal sum,
fused multiply-add, lower precision, vectorized logarithm, new optimizer or
structured recurrence. Masks, record boundaries, full Q/normalizer, iteration
count, seed stream and repeated-block multiplicity remain unchanged.

The [pre-validation derivation](phase-3-simd-derivation.md) documents formulas,
layout lifetime, tails and unsafe-access proofs. Model, model-workspace, dense HMM,
Q, optimizer and EM core files remain byte-identical to Phase 2. AVX only operates
behind CPU/OS detection on x86-64. Auto falls back on unsupported hardware or fewer
than four states; a forced unsupported AVX request fails before output creation.
AVX2 is not required. Other architectures retain generic code; ARM execution and
NEON remain not_run.

This is a strict SIMD submilestone. The broader Phase 3 structured-matrix/factored-Q
work is still open. The additional backward layout costs `3*K*K*8` bytes per
prepared model (98,304 bytes at K64). It is a copy of existing products, not a new
calculation. Existing conservative worker admission includes model-layout reserve;
its policy is still an estimate rather than an OS memory limit. Decoding retains
the unchanged dense implementation.

## Correctness and safety evidence

**340 inherited differential checks pass**: dense 113, forced-generic CPU 113,
and automatic AVX CPU 114. All three paths run the complete 30 fixed K23/N30
bootstrap trajectories. Exactly 27 remain finite and indices 16, 26 and 28 retain
the previously identified vanilla pathologies. Only the single honest `MM Version`
line is excluded from legacy byte comparisons. Numerical tolerances were not
relaxed. [Gate and provenance](../bench/phase-3-validation.json).

**Ten complete internal snapshot pairs** compare 37,789 ordered events and
43,513,458 finite numeric fields, with zero mismatches. They include the complete
K64/N1 model/message/count/optimizer trace for automatic AVX. Finite values and
signed zero compare exactly; NaN/Inf classes are handled separately. The large
unchanged Phase 1 independent-enumeration trace remains historical evidence rather
than being regenerated. No selected trace is truncated.

**32 unit tests pass in debug and release.** The original exhaustive short-string
control remains, plus all 3,279 strings of lengths 1–7 on a four-state model to
exercise actual vector lanes. Additional tests cover 18 state sizes including
all four tail remainders, growing/shrinking and poisoned buffers, all SIMD modes,
model updates, missingness, nonfinite models, signed zero, subnormals, infinities,
unaligned subslices and output canaries. Safe wrappers reject bad shapes before
entering intrinsics. Dispatch simulation covers AVX absence; it does not substitute
for a physical no-AVX-machine test. [Build/test logs](../bench/phase-3-cargo-checks.json).

**38 CLI self-review controls pass**, including original-C comparisons for 11
state sizes under auto/off/avx, output preservation for invalid selections, and
three one-worker bootstrap batches with randomized initialization across modes.
These are self-review controls; no independent reviewer or subagent was used.
[Controls](../bench/phase-3-review.json).

**60 one-worker scheduler fits pass** across forward/reverse task order, with
exact source indices, seeds, output and cache accounting. Cache on/off and snapshot
bypass agree; three extra randomized bootstrap comparisons match instrumented C.
All tested K23/K64 automatic fits select AVX; small-state fallback is explicit in
review statistics. No runtime rescue or numerical fallback is used for failed
models. [Serial integration gate](../bench/phase-3-scheduler.json).

The Phase 2 executable already contained packed SSE2 operations. Static inspection
of the new three specialized functions finds 27 packed AVX arithmetic instruction
sites and no FMA or horizontal-add instructions. This is instruction-site evidence,
not a runtime instruction count. [Baseline inspection](../bench/phase-3-baseline-assembly.json),
[new inspection](../bench/phase-3-assembly.json).

## Single-fit measurements

The host is the same Intel i5-12600K, x86-64 Linux/glibc 2.39, with affinity restricted
to logical CPU 0 and nice level 10. The user had other CPU work running. Measurements
are sequential and rotate implementation order, with one warmup and five measured
runs each. No build, correctness suite, profiler or archive compression ran alongside
the benchmark. Inputs are the same finite synthetic 13,200-bin K23/N30 fit and
52,800-bin K64/N5 partial trajectory. All measured and warmup outputs match.

CPU time below is user+system time charged to completed child processes, measured
with `getrusage`, including the small timing wrapper. It reduces sensitivity to
waiting for a CPU; it does not eliminate shared-cache, SMT, frequency or memory
contention. Wall ranges and per-run values are retained. These are local diagnostic
ratios, not statistically established portable improvements.

| Case | Vanilla CPU time | Phase 2 CPU time | SIMD CPU time | Phase 2 / SIMD | Vanilla / SIMD |
|---|---:|---:|---:|---:|---:|
| 23 states / 30 rounds | 0.413 s | 0.315 s | 0.281 s | 1.122× | 1.469× |
| 64 states / 5 rounds | 1.559 s | 1.386 s | 1.056 s | 1.312× | 1.476× |

Median wall times for C/Phase2/SIMD are 0.413/0.315/0.286 seconds at K23 and
2.031/1.602/1.174 seconds at K64. SIMD wall ranges are 0.272–0.607 and 1.026–1.727
seconds respectively, showing why the CPU-time comparison is also reported.
The current generic `--simd off` path is separately measured: CPU medians
0.318 and 1.413 seconds, close to the preserved Phase 2 comparison.

Median per-process maximum resident memory:

| Case | Vanilla | Phase 2 | SIMD |
|---|---:|---:|---:|
| 23 states / 30 rounds | 4,780 KiB | 5,260 KiB | 5,284 KiB |
| 64 states / 5 rounds | 27,332 KiB | 26,768 KiB | 26,908 KiB |

Buffer storage remains proportional to longest-record length times states.
There is no substantial peak-memory reduction or checkpointing claim.
[Full raw measurements, commands, ranges and hashes](../bench/phase-3-benchmark.json).

## Serial bootstrap result: no clear incremental gain

All 30 materialized-equivalent fits run with **one worker**, including the three
known nonfinite reference cases. Each implementation has one warmup and three
measured batches, with rotating order. C receives materialized input; Rust performs
the same resampling and writes its normal draw/stats/manifest files. No snapshots
or phase timers are enabled. Every output is compared after fitting; every child
must exit successfully. Rust manifests must admit exactly one worker.

| Implementation | Median CPU time | CPU range | Median wall time | Wall range |
|---|---:|---:|---:|---:|
| Vanilla | 18.714 s | 14.904–18.940 s | 19.974 s | 19.470–21.724 s |
| Phase 2 CPU | 11.514 s | 9.149–14.094 s | 11.563 s | 9.487–14.186 s |
| SIMD CPU | 11.454 s | 9.496–11.607 s | 12.352 s | 11.570–16.485 s |

The incremental Phase2/SIMD ratio is **1.005× CPU time and 0.936× wall time**.
The overlapping variation and slower wall median do not establish a bootstrap
improvement. The SIMD build is still faster than vanilla in this set (1.634× CPU,
1.617× wall), but most of that benefit was already present in Phase 2. These
pathology-containing batches measure mechanics, not finite production inference.
No multiworker speedup is extrapolated from them.

Median maximum RSS is 3,064 KiB for an individual sequential C child, 3,976 KiB
for the one-worker Phase 2 process and 3,960 KiB for SIMD. The C value excludes its
Python parent, whereas Rust includes its queue; these are labeled process peaks,
not a physical-memory-saving ratio. Cache accounting remains 11,730 visits,
7,740 evaluations and 3,990 hits per batch (34.02%).

## Isolated kernels and remaining work

Five alternating generic/AVX kernel pairs, after warmups and exact checks, give
median timed-section wall ratios 1.235× at K23 (0.097049/0.078582 seconds) and
2.294× at K64 (0.962050/0.419435 seconds). Prepared-layout construction is included;
process CPU time also includes a separate correctness check outside that section.
These shared-host kernel ratios must not be substituted for inference speedups.
The initial one-pair implementation probe remains in `bench/phase-3/` and is not
accepted repeated performance evidence.

A separate [E/M timing diagnostic](../bench/phase-3-profile.json) ran before the
benchmark. Its wall timers varied heavily with contention (even the unchanged
M-step varied substantially), so no precise CPU attribution or new Amdahl bound
is inferred from that sample. The model/Q/optimizer code is unchanged. The neutral
bootstrap result and earlier profiling motivate further work on the remaining
objective/model calculations, alongside real-workload profiling; SIMD alone is
not a path to a supported 10× claim.

## Build, provenance, reproduction and limits

Rust remains pinned to 1.90.0 with zero registry dependencies, release opt-level 2,
one codegen unit and no LTO, native target flag, fast-math or new external math
library. Core transcendental functions still use the same system libm as C.
Cargo jobs and test threads were one; descendants inherited one-CPU affinity.
[Build source/library hashes](../bench/phase-3-build.json).

Delivered executable SHA-256:
`8e417125208343026d56bae1b540b058371e4a0e949ca148a73c696b217f637b`.
The preserved Phase 2 digest is
`fd866573a007003d2388137270ec24f14acb436c42c7084ab8dac076fdabb59a`.
Correctness and timings use read-only frozen copies of these and the pinned C
executables. Source and binary guards prevent mixing rebuilds into evidence.

The [README](../README.md#reproduce-this-milestone) lists the actual build, isolated,
review, full-gate, one-worker and timing commands. Reports retain exact arguments,
return codes and hashes. Source, derivation, tests and timings are committed
together. The [package](../PACKAGING.md) includes them and the executable; complete
large snapshots remain local with explicit omission hashes and reproduction steps.
Prior archives remain unchanged.

Real user data/settings/splitting/callability provenance, full-genome memory,
physical no-AVX hardware, ARM/NEON, AVX-512, other operating systems, CUDA,
multiworker SIMD throughput, disk/memory exhaustion and termination recovery are
**not_run**. No vector-log substitution, model change, structured recurrence,
checkpoint/resume or altered bootstrap procedure is included. Phase 3a is complete;
production validation and the broader structured CPU milestone remain open.
