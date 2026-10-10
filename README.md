# PSMC in Rust — strict CPU optimization

This Rust workspace implements the original PSMC model, full expected counts,
Hooke–Jeeves optimizer, EM fitting, input handling and legacy output. Version 0.2
adds an optimized CPU backend, reusable numerical buffers, repeated-block caching,
and a bounded parallel bootstrap runner. Double precision, summation order,
sequence boundaries and the statistical method are preserved.

Use `--backend cpu` for the optimized path. The default remains `dense`, the
retained scalar oracle. Read the [Phase 2 report](docs/phase-2-report.md) for
measured speed, exact comparisons and limitations. The pinned external reference is
[`lh3/psmc` at 82fa2ada83ee463fe1251b562ae3d60e82d7ad6a](https://github.com/lh3/psmc/tree/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a).
The [Phase 1 report](docs/phase-1-report.md) and
[Phase 0 decision](docs/phase-0-decision.md) retain historical evidence.

## Build and run

Run from this directory:

```bash
mkdir -p work
cargo build --release --locked --offline
cargo test --workspace --locked --offline
target/release/psmc-rs --backend cpu --seed 42 -p '4+5*3+4' -N 30 \
  -t 15 -r 4 -I 0 -o work/example.psmc tests/fixtures/workload.psmcfa
```

The supplied executable is `bin/psmc-rs`; `bin/psmc-rs-phase1` preserves the
previous dense release. Rust 1.90.0 is pinned and must already be installed for
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
bin/psmc-rs bootstrap --backend cpu --replicates 30 --workers 4 \
  --memory-mib 2048 --seed 20261009 --output-dir work/bootstrap-example \
  -p '4+5*3+4' -N 30 -t 15 -r 4 -I 0 tests/fixtures/blocks.psmcfa
```

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

Build normal and instrumented C following [the reference instructions](README_PHASE0.md),
then run from this directory (Python 3.11+ for provenance tools):

```bash
cargo fmt --all --check
cargo test --workspace --locked --offline
cargo test --workspace --release --locked --offline
python3 bench/phase2_build.py
python3 bench/phase2_validate.py --run
python3 bench/phase2_scheduler.py --run
python3 bench/phase2-review.py --binary target/release/psmc-rs
python3 -m unittest discover -s bench -p test_phase2_harness.py
# Only after tests/builds finish; no profiling/compression alongside measurement:
python3 bench/phase2_benchmark.py --run
# Separate diagnostic, outside the measurement window:
python3 bench/phase2_profile.py
```

Preserve parent reports before rerunning. Phase 2 uses timestamped raw directories
and frozen executable copies. The [protocol](docs/phase-2-validation-protocol.md)
states which large Phase 1 traces are retained rather than regenerated. No test
tolerance was loosened. Historical Phase 1 runners remain for the archived
Phase 1 source; do not overwrite their reports by rerunning them against 0.2.

## Source and package

- `crates/psmc-core`: dense f64 oracle, model workspace, optimizer, EM and RNG.
- `crates/psmc-cpu`: reusable HMM messages, prepared model and repeated-block cache.
- `crates/psmc-io`: parsing, gzip and ordered bootstrap indices.
- `crates/psmc-cli`: single fit, bounded batch queue, legacy output and diagnostics.
- `reference`, `tests/fixtures`, `bench`, `docs`: pinned C, synthetic inputs,
  reproducible evidence, derivations and limitations.

Unsafe code remains confined to system math/formatting and owned gzip input.
Inference does not call C PSMC. Original MIT notices remain in translated sources
and [LICENSE.psmc.txt](reference/LICENSE.psmc.txt). No user genome was accessed
or uploaded. The supplied execution plan is context, not proof of implementation;
this CPU milestone follows the user's explicit optimization request.

The compact `psmc-rust-phase-2.zip` contains source, executable, fixtures and
inspectable evidence. Large snapshots and build environments remain local with
explicit omission hashes/reproduction instructions. See [PACKAGING.md](PACKAGING.md).
The Phase 0 and Phase 1 archives remain unchanged.
