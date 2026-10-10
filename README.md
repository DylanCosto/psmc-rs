# PSMC in Rust — SIMD and parallel bootstraps

This Rust workspace implements the original PSMC model, full expected counts,
Hooke–Jeeves optimizer, EM fitting, input handling and legacy output. Version 0.3.3
widens the ordered 64-state AVX message and count kernels to 32 independent
destinations. The eight-site count tiles and bounded message capacity remain. Each fit uses one numerical
thread; independent bootstrap fits can use all available CPUs. Reusable
buffers, exact repeated-block caching and the dense oracle remain available. Double precision, summation order,
sequence boundaries and the statistical method are preserved.

Use `--backend cpu` for the optimized path. The default remains `dense`, the
retained scalar oracle. The [parallel report](docs/parallel-report.md) validates
16-worker synthetic batches against already-parallel vanilla. The
[human-input report](docs/hg-benchmark-report.md) adds a public HG001/NA12878
chromosome 22 test with full 64-state, 30-iteration fits. The [CPU headroom report](docs/cpu-next-optimization.md)
records v0.3.3: 2.1% lower median human batch wall time and 2.8% lower CPU time
versus v0.3.2 across six paired measurements, with overlapping ranges. It also
validates a larger public HG002 chromosome 1 input exactly against vanilla PSMC.
The [count-kernel report](docs/counts-optimization.md) retains the v0.3.2 measurements. The [CPU campaign report](docs/cpu-campaign-report.md)
retains the previous kernel campaign evidence. The [Phase 3a report](docs/phase-3-simd-report.md)
retains the previous SIMD release evidence. The pinned external reference is
[`lh3/psmc` at 82fa2ada83ee463fe1251b562ae3d60e82d7ad6a](https://github.com/lh3/psmc/tree/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a).
The [Phase 1 report](docs/phase-1-report.md) and
[Phase 0 decision](docs/phase-0-decision.md) retain historical evidence.

## Build and run

Run from this directory:

```bash
mkdir -p work
cargo build --release --locked --offline --jobs 1
cargo test --workspace --locked --offline --jobs 1 -- --test-threads=1
target/release/psmc-rs --backend cpu --seed 42 -p '4+5*3+4' -N 30 \
  -t 15 -r 4 -I 0 -o work/example.psmc tests/fixtures/workload.psmcfa
```

The supplied executable is `bin/psmc-rs`; `bin/psmc-rs-v0.3.2` preserves the
previous release, and `bin/psmc-rs-v0.3.1` the earlier CPU release; `bin/psmc-rs-phase3a` preserves the earlier SIMD executable;
`bin/psmc-rs-phase2` preserves the prior
optimized CPU release and `bin/psmc-rs-phase1` the original dense release. Rust 1.90.0 is pinned and must already be installed for
an offline build. There are no registry dependencies. The tested stack is
x86-64 Linux/glibc 2.39 using system `libm`, `libc` and `libz.so.1`. No CUDA,
zlib headers or Python environment is needed to build or run inference.
Other architectures and operating systems have not passed the numerical gate.

`--help` lists supported options. Plain or gzip FASTA/FASTQ input is accepted;
`-` reads stdin for a single fit. The original T/K/N encoding and aliases remain
supported. Records remain independent HMM sequences; missing sites carry transitions.

| Options | Behavior |
|---|---|
| `-p -N -t -r -l -I` | Pattern, iteration count, maximum time, theta/rho ratio, grid alpha, random initialization |
| `-i -o` | Raw supplied parameters and legacy output file |
| `-b` | One original ordered record bootstrap with the nearest-length stop rule |
| `-d -D -s -C` | Posterior segments, full posterior, forward scales, decoding transition cap |
| `-T` | Original divergence parameter, with supplied-file restrictions below |
| `--seed INTEGER` | Replay of the original srand48/drand48 stream |
| `--mode strict` | Only implemented numerical mode |
| `--backend dense\|cpu` | Dense oracle (default) or optimized CPU engine |
| `--simd auto\|off\|avx` | CPU dispatch: automatic (default), generic CPU, or require AVX support |
| `--cache on\|off` | Per-expectation repeated-block cache for CPU; default on |
| `--stats FILE` | Counters and separately instrumented E/M timing for a single fit |
| `--snapshot FILE` | Test-only JSONL matrices, messages, counts and optimizer callbacks |

The original `-c` and simulation option `-S` are explicitly rejected. `-S` is
not a seed option. Equivalent/research modes, GPU kernels, VCF/long-read input,
checkpoint/resume and new plotting commands are not implemented.

## Run independent bootstraps

Supply blocks already split by your established preprocessing procedure. This
runner does not introduce new HMM boundaries or perform splitting.

```bash
bin/psmc-rs bootstrap --backend cpu --replicates 30 --workers 16 \
  --memory-mib 2048 --seed 20261009 --output-dir work/bootstrap-example \
  -p '4+5*3+4' -N 30 -t 15 -r 4 -I 0 tests/fixtures/blocks.psmcfa
```

The current full-core configuration uses **16 workers** on this tested 16-logical-CPU
host. The v0.3.3 campaign retested 8/10/16 workers: 16 had the shortest elapsed
time, while 10 physical-core workers used less total CPU time. Omit `--workers` to request the available CPU count on another machine;
memory admission may reduce it. Single fits remain single-threaded. The parallel
milestone validates the existing 0.3.1 queue; the slower experimental scheduling
change was rejected. Historical SIMD measurements used one worker.

The destination must not exist. Replicate `i` uses seed `base + i`, consumes the
same ordered bootstrap draws and then the same initialization RNG stream as an
independent original fit. Every repeated block occurrence is added in order,
even when its calculation is cached. Observations are shared through references.

One scoped-thread queue runs independent fits. Each fit has one numerical thread;
there is no nested pool. The admitted count is bounded by requested workers,
replicates, reported available CPUs and the memory estimate. The default is 30
replicates, available CPU workers and a 2048 MiB estimated budget. Specify your
worker limit explicitly when comparing with an already parallel workflow.

`--memory-mib` is a conservative admission estimate, **not an OS-enforced RSS
limit**. Input loading precedes admission. The estimate includes retained result
metadata, draw storage, message capacity, count caches and per-worker overhead.
The manifest records the estimate and actual admitted count. Full-genome memory,
hardware exhaustion and termination recovery have not been validated.

Each completed fit creates `replicate-NN.psmc`, `.stats.json` and `.draws.jsonl`.
`manifest.json` records ordered source indices, seeds, lengths, workers, failures
and nonfinite fits. The input fingerprint is explicitly noncryptographic FNV-1a;
benchmark provenance separately records source SHA-256. `--task-order reverse`
is a scheduling diagnostic; it does not change sampling or reductions. Batch
phase timers are disabled (`profile_enabled: false`, seconds zero); counters
remain active. Failed jobs are reported, partial files retained, other jobs
finish, and the batch exits with failure. No atomic resume is claimed.

## SIMD selection and exactness

`--backend cpu` defaults to `--simd auto`. On tested x86-64 hardware with CPU/OS
AVX support, models with at least four states use four independent f64 lanes.
Smaller models and unsupported hardware use the generic CPU path. `--simd off`
disables the explicit AVX kernels; ordinary compiler optimizations, including
baseline SSE2 where available, remain enabled. `--simd avx` requires CPU/OS AVX
support and the CPU backend; unsupported requests fail before opening outputs.
Small shapes still use scalar tails. `--stats` reports both requested and selected
paths (`simd_requested`, `simd_selected`). Dense reports `scalar-dense`.

AVX does not add worker threads. Each lane retains the original ordered adds,
multiplies and divisions; there is no FMA or horizontal reduction. The additional
backward layout is copied from the exact existing emission-transition products.
The [derivation](docs/phase-3-simd-derivation.md) documents bounds checks and the
small isolated unsafe intrinsic module. Default compiler target features stay
portable; this is runtime dispatch, not a globally native-only executable.
ARM NEON, AVX-512 and non-x86-64 execution remain unvalidated; other architectures
retain the generic path. Explicit AVX support here does not require AVX2.

## Compatibility and limits

Strict output comparisons exclude only the single honest `MM Version` line.
All other bytes, including numerical metadata, match on the tested stack.
Internal finite values and signed zero compare exactly. This does not promise
universal bitwise equality across compilers, libraries or machines.

The [source contract](docs/reference-contract.md),
[math contract](MATH_AND_COMPATIBILITY.md),
[engineering derivation](docs/phase-2-engineering.md) and
[validation policy](VALIDATION_AND_BENCHMARKS.md) describe the preserved behavior:
per-record tiny counts, the final-site emission-count omission, full-count Q
normalizer and final optimizer callback side effects. The dense HMM, model
update and optimizer implementations remain available as independent oracles.

Some synthetic inputs make vanilla PSMC produce NaN/Inf. Rust retains these
results and warns when printed fit records are nonfinite, including RI-only
failures. Initial round-zero `RI inf` alone is expected. A successful process
exit is not a finite-inference certificate. The 30-fit synthetic fixture contains
27 finite fits and three known reference pathologies; their output parity and
batch timings are labeled separately from valid finite inference.

Malformed/empty/non-ASCII records, truncated quality/gzip data, negative iteration
counts, malformed patterns and unsafe supplied-grid/divergence combinations are
rejected. All-missing selected input requires explicit initial parameters, checked
before opening single-fit outputs. Parameter files use decimal/exponent numbers;
remove the `PA` prefix before passing a report line to `-i`. An explicit time-grid
file cannot also supply divergence; an ordinary file with `-T` must include its
own trailing divergence. Patterns are limited to 255 free groups and the legacy
signed-int state limit; bootstrap raw length is limited to INT_MAX.

Input/output aliases, hardlinks, redirected Linux standard streams and dangling
output symlinks are checked. Output, stats, snapshots and traces require separate
paths. Successful validation does not make streamed file writes atomic.

Snapshots are large and expensive. With `--backend cpu`, they execute the CPU
workspace path but visibly bypass the count-only cache to expose every
occurrence's messages. Dense snapshots retain the dense oracle path.
Use them for correctness tests, never throughput measurements. `PSMC_SEED`,
`PSMC_SNAPSHOT` and `PSMC_BOOTSTRAP_TRACE` support the single-fit harness; unset
snapshot/trace variables before batch runs. Explicit seed/snapshot flags take
precedence. Disable `--stats` phase timers for ordinary throughput comparisons.

The user's real input, command, splitting/mask provenance and worker budget are
still unavailable. All reported measurements use synthetic fixtures. Tenfold
acceleration, production runtime and GPU performance remain unproven.

## Reproduce this milestone

Build the C references using [the retained instructions](README_PHASE0.md).
Use one allowed logical CPU and low scheduling priority while other work runs.
Here CPU 0 is the tested affinity; choose an allowed CPU on another machine.
All commands below are sequential. Do not run timing with builds/tests/profiling.

```bash
taskset -c 0 nice -n 10 env CARGO_BUILD_JOBS=1 RUST_TEST_THREADS=1 \
  cargo test --workspace --release --locked --offline --jobs 1 -- --test-threads=1
taskset -c 0 nice -n 10 cargo build --release --locked --offline --jobs 1 \
  -p psmc-cpu --example simd_bench
taskset -c 0 nice -n 10 python3 bench/phase3_build.py
taskset -c 0 nice -n 10 python3 bench/phase3_review.py
taskset -c 0 nice -n 10 python3 bench/phase3_validate.py --run
taskset -c 0 nice -n 10 python3 bench/phase3_scheduler.py --run --workers 1
taskset -c 0 nice -n 10 python3 bench/phase3_benchmark.py --run
```

The build remains Rust 1.90.0 with no registry dependencies. Raw gate/benchmark
runs use timestamped directories and frozen executable copies; preserve parent
reports before rerunning. The SIMD gate adds the complete K64 internal trace on
the automatic CPU path. No tolerance was relaxed. Historical Phase 1/2 runners
and reports describe those archived source versions; do not overwrite them with
new runs. The one-CPU runners reject broad affinity and the scheduler gate rejects
worker counts above one. Wall time is sensitive to shared CPU load; per-process
CPU time and ranges are also reported.

## Source and package

- `crates/psmc-core`: dense f64 oracle, model workspace, optimizer, EM and RNG.
- `crates/psmc-cpu`: reusable HMM messages, prepared model and repeated-block cache.
- `crates/psmc-io`: parsing, gzip and ordered bootstrap indices.
- `crates/psmc-cli`: single fit, bounded batch queue, legacy output and diagnostics.
- `reference`, `tests/fixtures`, `bench`, `docs`: pinned C, synthetic inputs,
  reproducible evidence, derivations and limitations.

Unsafe code is confined to system math/formatting, owned gzip input and the
checked, runtime-guarded AVX intrinsic module.
Inference does not call C PSMC. Original MIT notices remain in translated sources
and [LICENSE.psmc.txt](reference/LICENSE.psmc.txt). No user genome was accessed
or uploaded. The supplied execution plan is context, not proof of implementation;
this CPU milestone follows the user's explicit optimization request.

The compact `psmc-rust-phase-3-simd.zip` contains source, executable, fixtures and
inspectable evidence. Large snapshots and build environments remain local with
explicit omission hashes/reproduction instructions. See [PACKAGING.md](PACKAGING.md).
The Phase 0, Phase 1 and Phase 2 archives remain unchanged.
