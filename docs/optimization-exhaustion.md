# Remaining optimization campaign

Status: complete; CPU v0.4.1 accepted and installed. Baseline source is `709831a`
(v0.4.0); the CPU timing baseline is the retained v0.3.3 executable. The frozen
v0.4.1 build passes performance, compatibility and delivery gates. This campaign
inventories credible remaining approaches under exact vanilla compatibility on
the available i5-12600K and RTX 5060 Ti.

Environment: x86-64 Linux, 32 GB host RAM, six performance cores with SMT plus
four efficiency cores (16 logical CPUs), RTX 5060 Ti 16 GB, CUDA driver 595.91.07
and NVRTC 12.9. Rust 1.90.0 uses the retained release profile (optimization level
2, one codegen unit, no LTO). CPU builds remain generic with runtime AVX dispatch.
[`exhaust-environment.json`](../bench/exhaust-environment.json) records the
machine/toolchain details and baseline hashes. The pinned vanilla reference is
`lh3/psmc` commit `82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`.

## Complete-workload CPU result

One warmup per executable and three alternating measured pairs ran all 30 fixed
HG001 chromosome 22 bootstraps, K64, N30, with 16 workers. All 240 outputs,
including warmups, match the pinned vanilla output except its single version
line; bootstrap draws and record multiplicity also match.

| Metric | Previous CPU v0.3.3 | Accepted CPU v0.4.1 |
|---|---:|---:|
| Median elapsed seconds | 50.1408 | 47.0875 |
| Measured elapsed range, seconds | 49.1189–52.4605 | 46.5871–47.8286 |
| Median aggregate CPU seconds | 656.51 | 612.47 |
| Median peak RSS, KiB | 1,315,464 | 1,315,368 |

Elapsed time falls **6.09%** and aggregate CPU time falls **6.71%**, with all
three pairs faster. This is an incremental comparison against the previous
optimized Rust release, not a new comparison against vanilla performance and
not a claim of a tenfold speedup. RSS is essentially unchanged. The shared
desktop host and three pairs limit generalization. Exact commands, every run,
binary/input hashes and acceptance calculations are in
[`exhaust-acceptance.json`](../bench/exhaust-acceptance.json).

## Numerical derivations and predeclared gates

CPU count variants keep each cell's recurrence
`A[k,l] = A[k,l] + ((forward[u,k] * ae[z,k,l]) * backward[u+1,l])`,
starting at the same tiny initializer and visiting sites in ascending order.
Larger tiles change only register lifetime. Joint-source variants load one
backward vector for two or four independent source rows. No lane reduction,
fused arithmetic, new sequence boundary or dropped observation is introduced.
Each 64-state block exactly divides the matrix; existing dispatch/shape guards
remain. The unchanged scalar/dense implementations are independent oracles.

Pinned CUDA experiments copy the same bytes into owned host staging buffers,
then enqueue copies and kernels on the worker's own stream. That stream provides
copy-before-use and kernel-before-next-write ordering. Two host banks allow two
tiles to be queued; a stream drain precedes bank reuse or allocation growth, and
precedes returning final counts. Model upload drains the previous model's work.
Drop drains the stream before freeing host/device storage. These are disposable
prototypes: production memory admission must account for any additional pinned
storage before a candidate can ship. Launch geometry changes ownership scheduling,
not arithmetic. GPU failures remain errors, with no automatic fallback.

Full-model/objective memoization, if exercised, keys exact normalized parameter
bits, restores every live model field, and preserves every optimizer callback.
Entries are bounded and cleared at each E-step, so Q cannot cross count snapshots.
Nonfinite parameters bypass reuse. This is distinct from earlier per-probability
log caches. Prototype settings are fixed within a fit; any production API must
also invalidate on settings changes. CPU-native compiler flags do not permit
fast-math or FMA contraction and require fresh exactness checks.

Single-fit screens use one warmup and three rotated measured runs. Final CPU
promotion requires >=2% lower median complete 30-bootstrap wall time, lower
median CPU time, and >=2/3 faster alternating pairs following one warmup each.
GPU promotion additionally requires >=5% wall improvement versus recommended CPU.
No optional repetitions rescue a failed result. All outputs, including failed
or pathological cases, are retained. Shared-host noise limits generalization.

## Opportunity ledger

| Area | Prior evidence / remaining experiment | Status |
|---|---|---|
| Ordered count register/cache tiles and emission fusion | Six initial variants plus three refinements; joint two-source, 16-site tiles combined with AVX normalization and emission updates | Accepted: 6.09% lower complete-batch elapsed time; all final regressions pass |
| Forward/backward SIMD | Dedicated K64 AVX32 already accepted; generic wider/tail paths previously regressed smaller shapes | Prior measured decisions retained |
| Sequence-count caching | Exact duplicate reuse already enabled; multiplicity retained | Implemented |
| Cross-iteration/cross-fit caching | Parameters and counts change; cannot key by observation alone | Exactness constraint |
| Q/model reuse | Full-candidate memoization regresses K23 by 8–10%; inspected C traces repeat only 0.8–3.4% of parameter vectors | Rejected |
| Compiler optimization | New native codegen is slightly slower on the main fit; prior opt3/LTO/PGO failures retained | Rejected |
| Allocation and layout | HG002 attributes ~1.1% to workspace setup and negligible prepared layouts; prior reservation/dispatch regressions retained | No material untested allocation bottleneck identified |
| Memory checkpointing | Exact prior prototype reduces RSS but adds recomputation; new HG002 setup is ~1.1% of CPU time | Prior measured tradeoff retained |
| CPU scheduling | Two complete-batch rotations: all16 ~49.61s mean, P-core12 ~57.29s, physical10 ~52.67s, P-core6 ~62.00s, all12 ~52.17s | Retain 16 workers |
| GPU transfers | Pinned worker-local copies and two-bank staging: 66.00–66.95s vs CPU 48.95s | Rejected for speed; CPU use also increases |
| GPU occupancy and tile size | 32/64-thread blocks, larger tiles, two/four count chains per thread all remain slower than CPU | Rejected |
| Resident GPU messages | At 128 independent records, GPU kernels 0.908s vs CPU 0.611s (10 workers) or 0.635s (16 workers), including additional CPU work | Rejected on this hardware |
| GPU record/CPU overlap | Lookahead plus larger tiles improves GPU to 62.83s, still behind CPU 48.95s | Rejected for speed |
| GPU waiting and mixed devices | Combined blocking/large-tile/lookahead/CPU candidate: 8 GPU fits gives 45.70s vs CPU-only 46.41s, below the 5% threshold; 15/30 GPU fits are slower | Rejected for speed; CPU-saving tradeoff recorded |
| Parallel reduction / scans / structured algebra | Prior exact-bit counterexamples; changing grouping changes optimizer trajectories | Excluded from strict mode |
| Lower precision, approximate math, fewer states/rounds | Changes numerical/scientific contract | Excluded from this request |
| NEON / AVX-512 / other GPU hardware | Current host is x86 AVX, no supported AVX-512 or ARM execution environment | Hardware-limited, not tested |
| I/O and parsing | Existing diagnostics attribute only small residual time on available inputs | No measured major bottleneck |

Human fitting screens retain full input records and full N30 fits. Isolated
kernel/occupancy probes are labeled separately. HG002 chr1 is a larger held-out
chromosome, not a whole genome or the user's private workload.

## Reproduction

New runners are `bench/exhaust_*.py`; their reports are `bench/exhaust-*.json`.
Disposable sources, binaries, logs and raw outputs live under ignored
`work/exhaust/`. Earlier release evidence remains intact.

The runners deliberately refuse to overwrite most experiment directories. Rerun
in a separate checkout with the pinned reference, documented public inputs and
retained oracle fixtures prepared as described in the earlier reports. Do not
erase evidence merely to make a command run. Source-generating experiments
archive commit `709831a`; each report records its build commands, hashes, fit
arguments and raw output paths. `exhaust_more_v1.py` preserves the exact runner
used by the original native/memo/normalization screen. The later
`exhaust_more.py` adds an optional K64-only dispatch for combined experiments;
the original runner hash is checked explicitly in the final audit.

Campaign commands actually used, in dependency order (CPU screens have separate
`build` and `screen` invocations):

```text
python3 bench/exhaust_profile.py
python3 bench/exhaust_cpu.py build
python3 bench/exhaust_cpu.py screen
python3 bench/exhaust_more.py build
python3 bench/exhaust_more.py screen
python3 bench/exhaust_reuse.py
python3 bench/exhaust_refine.py build
python3 bench/exhaust_refine.py screen
python3 bench/exhaust_fusion.py build
python3 bench/exhaust_fusion.py screen
python3 bench/exhaust_unroll.py build
python3 bench/exhaust_unroll.py screen
python3 bench/exhaust_schedule.py
python3 bench/exhaust_cuda.py build
python3 bench/exhaust_cuda.py screen
python3 bench/exhaust_pipeline.py
python3 bench/exhaust_wait_policy.py
python3 bench/exhaust_gpu_batches.py
python3 bench/exhaust_hybrid.py
python3 bench/exhaust_resident.py
python3 bench/exhaust_resident_cpu.py
python3 bench/exhaust_final_build.py
python3 bench/exhaust_batches.py --candidate work/exhaust/final-build/psmc-rs-cpu --label acceptance
python3 bench/exhaust_gpu_lanes.py
python3 bench/exhaust_resident128.py
python3 bench/exhaust_hybrid_combo.py
python3 bench/exhaust_resident128_cpu.py
taskset -c 0 python3 bench/phase3_validate.py --run --candidate work/exhaust/final-build/psmc-rs-cpu --report bench/exhaust-full-validation.json
python3 bench/exhaust_validate.py --candidate work/exhaust/final-build/psmc-rs-cpu
python3 bench/exhaust_cuda_control.py
```

The final build runner records debug/release unit tests, hardware CUDA tests,
optional CUDA and CPU-only builds, and assembly checks. Its source and
configuration hashes identify the tested implementation independently of the
later documentation/evidence commit. The dense oracle, model, optimizer,
production CUDA kernel/driver and batch scheduler are unchanged.

## Frozen implementation and compatibility evidence

The frozen CPU v0.4.1 SHA-256 is
`566883bce56317b8d1720551373959fc3e2808538977240a45ff656cf9ebff43`.
The optional CUDA build, using the same CPU normalization change and unchanged
GPU kernel/driver, is
`4763281272d642f10dc42ac0879676b99d9f19158b0bf17bcf45de942fa6b8ff`.
Source/configuration hashes are in
[`exhaust-final-build.json`](../bench/exhaust-final-build.json).

The final source passes 39 debug unit tests (four hardware GPU tests explicitly
ignored in that command) and 43 release tests with all hardware tests enabled.
Assembly inspection finds packed AVX instructions and no FMA or horizontal
reductions in the inspected numerical functions. Direct tests cover unaligned
buffers/canaries, normalization division, tile boundaries, missing symbols,
last-site omission, tiny initializers, subnormals, signed zero and nonfinite classes.

The full C regression passes **340 checks and ten ordered internal traces**:
113 dense, 114 automatic CPU and 113 forced-scalar CPU checks. Each backend
retains the same 27 finite synthetic bootstraps and reference pathologies
16/26/28. Finite internal values and signed zero are compared by binary64 bits;
nonfinite classifications are checked separately. Only one output version line
is excluded from byte comparison. The unchanged core's exhaustive independent
path/Q enumeration retains prior evidence rather than being rerun; that exclusion
and the exact trace selection are explicit in
[`exhaust-full-validation.json`](../bench/exhaust-full-validation.json).

The additional **66 extended C fixtures** pass. Two alternating full-fit pairs
per public chromosome also pass exact C comparison. The descriptive two-run
means (equal to the two-point medians) are:

| Continuous input | CPU v0.3.3 seconds | CPU v0.4.1 seconds | Elapsed reduction |
|---|---:|---:|---:|
| HG001 chr22, 508,185 bins | 14.2016 | 13.5461 | 4.62% |
| HG002 chr1, 2,489,565 bins | 66.0076 | 60.4640 | 8.40% |

HG002 peak RSS remains ~2,514,900 KiB. These small held-out controls support the
primary bootstrap gate; they are not whole-genome or statistical significance
claims. All eight human outputs match vanilla. Thirty synthetic bootstraps with
one forward-order worker also match the same thirty fits with sixteen workers
and reversed task order. See
[`exhaust-validation.json`](../bench/exhaust-validation.json).
The optional CUDA build passes exact full HG001 and HG002 fits; the CPU-only
build explicitly rejects a CUDA request. No automatic backend fallback occurs.
See [`exhaust-cuda-control.json`](../bench/exhaust-cuda-control.json).
Production changes are confined to
`crates/psmc-cpu/src/lib.rs`, `crates/psmc-cpu/src/simd.rs`, the workspace version
and CLI version text, with documentation/evidence alongside them.

CUDA transfer semantics follow the official [Driver memory API](https://docs.nvidia.com/cuda/cuda-driver-api/cuda_driver_api/group__CUDA__MEM.html)
and [stream execution documentation](https://docs.nvidia.com/cuda/cuda-programming-guide/02-basics/asynchronous-execution.html).
Native code generation follows the [rustc codegen reference](https://doc.rust-lang.org/stable/rustc/codegen-options/index.html).

Additional mechanism: forward normalization currently occurs outside the AVX
message kernel. A candidate divides independent destinations by the unchanged
scalar scale using explicit AVX division (never reciprocal multiplication), with
scalar tails. Scale summation order is unchanged. A second candidate computes
emission counts beside each ascending transition tile, reusing hot message rows.
For each symbol/state the same `(f*b)*scale` terms are added in ascending site
order, including missing-symbol counts and the final-site omission. This is not
fusion with the descending backward sweep. These candidates require complete
trajectory gates before any production adoption.

Record-overlap prototype: the GPU may finish one record's transition counts while
CPU computes the next record's messages. A pending count object owns the previous
record's initial/emission counts and likelihood. Its device count array is drained
and downloaded before reuse. Aggregation and warnings are collected in original
record order, and duplicate records flush pending work before consulting the
same-snapshot cache. Singleton records retain tiny transition initializers without
a launch. Snapshots/profiling retain the original synchronous implementation.
This prototype changes scheduling only; both paths must produce identical fits.

Mixed-device experiment: a fixed, explicit prefix of the 30 bootstrap jobs selects
CUDA; remaining jobs select CPU. Each fit retains its own original seed and
records. This is a planned allocation of work, not a runtime failure fallback.
The experimental batch manifest's overall backend remains CUDA, while each
replicate's statistics identify its actual backend; the report records the split.
Any production version would require an explicit supported interface.

A further GPU scheduling mechanism is explicitly tested: CUDA's default wait
policy can spin on a CPU core while waiting for a kernel. Separate yielding (2)
and blocking (4) primary-context flag prototypes retain all arithmetic and
transfer dependencies. They set the same policy in every worker, including after
a context is recreated. These are process-local context settings, not machine
configuration changes. Official [primary-context API documentation](https://docs.nvidia.com/cuda/cuda-driver-api/cuda_driver_api/group__CUDA__PRIMARY__CTX.html)
explains the CPU scheduling tradeoff. Complete batch timing determines whether
reducing spin contention benefits this workload.

## Measured screening results

Fresh HG002 full-chromosome profiles (two exact C comparisons) assign ~44.5% of
CPU time to transition counts, ~25.2% forward, ~21.5% backward, ~4.1% other counts
and ~3.3% model/Q. Sections are instrumented and some are inclusive; these are
attribution, not release speed measurements.

The fused CPU candidate combines K64-only AVX normalization, two-source
16-destination transition blocks, 16-site tiles, and emission updates within
each tile. Its single-fit screen median is 9.7719s versus 10.0563s control.
The combined candidate without emission fusion is 9.9134s. Manual four-source
message-loop unrolling is slower in a separate control screen and is rejected.
Different screens have different baseline timing distributions. Small isolated
gains must not be treated as portable or additive; final artifact timing decides.

The CPU screens retain 184 full C-output comparisons across the initial tiles,
native/memo/normalization, refinement, fusion and unrolling experiments; the
CUDA single-fit screen adds 20. Reports are
[`exhaust-cpu.json`](../bench/exhaust-cpu.json),
[`exhaust-more.json`](../bench/exhaust-more.json),
[`exhaust-refine.json`](../bench/exhaust-refine.json),
[`exhaust-fusion.json`](../bench/exhaust-fusion.json),
[`exhaust-unroll.json`](../bench/exhaust-unroll.json) and
[`exhaust-cuda.json`](../bench/exhaust-cuda.json).

Resident GPU message kernels are exact for 1/8/16/32 independent record copies.
At 32 records, kernels alone take 0.6168s, versus 0.2153s (10 workers) or 0.2235s
(16 workers) for the measured CPU batch, which additionally includes emission
counts and likelihood. GPU allocation/transfers/full comparison take 3.2749s;
that diagnostic includes Python overhead and is not production inference timing.
These are synthetic occupancy probes, not whole-genome or bootstrap claims.

The final 128-record probe takes 0.9083s in GPU kernels and 5.3484s for the full
allocation/transfer/compute/Python-comparison diagnostic. The measured CPU
control (one warmup and three repetitions) takes a median 0.6112s with 10 workers
or 0.6353s with 16 workers, including emission counts and likelihood that the GPU
probe omits. All GPU forward/backward/scale arrays match the CPU fixture bytes.
Even the GPU-only kernel time is slower, so a fully resident exact message
implementation does not justify further integration on this device.

The final GPU kernel search assigns two or four independent count cells to each
thread. Each cell retains its original ascending site chain and explicit rounded
multiplies/adds. For state counts divisible by that grouping, aligned cell groups
stay in one source row and may share the exact same forward load. Other shapes
load each source independently, and partial final groups guard each cell. This
trades fewer resident threads for more independent arithmetic per thread; hardware
unit tests and full-batch measurements decide whether it hides latency usefully.
Both variants pass the CUDA unit gates and all 30 C comparisons, but take
66.4471s (two cells) and 67.2255s (four cells), versus the same screen's original
CUDA 64.7125s and CPU 48.9036s. Reject both.

## GPU and scheduling decisions

The following full 30-fit GPU screens are single runs per configuration, intended
for rejection/screening rather than release speed claims. Every output and
bootstrap selection matches its original C oracle. New pinned/overlap/wait/kernel
variants remain isolated prototypes; none changes the production GPU backend.

| Configuration | Elapsed seconds | Aggregate CPU seconds |
|---|---:|---:|
| CPU v0.3.3 control | 48.953 | 660.26 |
| Original CUDA | 70.411 | 531.50 |
| Worker-stream pinned staging | 66.948 | 842.78 |
| Two-bank stream pipeline | 66.003 | 837.38 |
| Pipeline, 32-thread blocks | 65.506 | 838.96 |
| Pipeline, 64-thread blocks | 66.045 | 837.59 |
| Original CUDA, 65,536-site tiles | 64.902 | 556.25 |
| Record lookahead | 71.069 | 518.41 |
| Lookahead, 65,536-site tiles | 62.832 | 451.63 |
| Yielding CPU waits | 71.892 | 533.04 |
| Blocking CPU waits | 67.048 | 365.85 |

The first mixed-device screen uses the original backend: 0/8/15/22 GPU jobs
take 50.342/53.889/57.899/61.844s. A predeclared final combination uses blocking
waits, large tiles, record lookahead and the provisional CPU optimizations:

| GPU fits out of 30 | Elapsed seconds | Aggregate CPU seconds |
|---|---:|---:|
| 0 | 46.412 | 616.70 |
| 8 | 45.701 | 571.89 |
| 15 | 53.382 | 465.43 |
| 30 | 61.601 | 355.94 |

The best mixed screen cuts elapsed time only 1.53%, below the predeclared 5%
threshold for GPU promotion, and its peak RSS rises from 1,315,504 to 1,422,668
KiB. Higher GPU shares save CPU consumption but take longer. No GPU configuration
merits a fresh paired acceptance campaign under the speed objective. These
results do not establish that GPU use is universally useless: freeing CPU
capacity is a different tradeoff, and other GPUs/arithmetic contracts are untested.

The core scheduling screen retains all 16 logical CPUs. Two opposite-order
rotations of five allocations check 300 full outputs; all16 has the shortest
mean elapsed time (49.61s). Ten physical-core workers save CPU consumption
(466.10s vs 652.11s) while taking longer (52.67s). No scheduler change ships.

## Scope and stopping rule

All identified opportunities now have measured outcomes or an explicit exactness,
hardware or input limitation. The final source change is limited to ordered K64
CPU kernels plus the version update and direct tests. Earlier exactness
counterexamples and measured rejections remain in the
[CPU headroom](cpu-next-optimization.md), [count-kernel](counts-optimization.md),
[CPU campaign](cpu-campaign-report.md) and [CUDA](cuda-report.md) reports.
This is an engineering stopping rule on the current machine, not a proof that
every conceivable algorithm, compiler setting or future device is exhausted.

No ARM/NEON, supported AVX-512 host, datacenter GPU, whole genome or private user
workload was tested. Hardware performance counters were unavailable under the
existing system policy; it was not changed. Instrumented section timings and
whole-device activity samples are diagnostics; GPU activity is not a measurement
of peak arithmetic throughput. No reduced precision, changed optimizer, reordered
sum, dropped repeated block or shortened fit is used. The next permitted project
milestone is broader real-workload validation and reliability. The current
optimization milestone is complete.


## Final audit and installed deliverable

`python3 bench/exhaust_audit.py` passes: 340 regression checks, ten ordered
traces, 66 extended fixtures, all 204 CPU/CUDA single-fit screen outputs, and
**1,230 human bootstrap outputs across 41 batches** rechecked against retained
vanilla outputs and replayed bootstrap draws. Source/configuration, prototype
sources, binaries, build logs and report hashes are checked and recorded in
[`exhaust-audit.json`](../bench/exhaust-audit.json). There are no numerical
mismatches in this campaign. Poor timings are retained as measured rejections.

`python3 bench/exhaust_install.py` installs the exact accepted CPU artifact as
`bin/psmc-rs` and `bin/psmc-rs-v0.4.1`. Use `--backend cpu`; the CLI's default
remains the dense oracle. The optional CUDA artifact is `bin/psmc-rs-cuda` and
remains experimental. Previous binaries are preserved as `bin/psmc-rs-v0.3.3`
and `bin/psmc-rs-cuda-v0.4.0`. Installed hashes and the accepted audit hash are in
[`exhaust-install.json`](../bench/exhaust-install.json). No new archive or external
publication is part of this milestone. The source, derivations, tests and
measurements are committed together locally.
