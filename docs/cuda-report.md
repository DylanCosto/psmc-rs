# Optional CUDA milestone (v0.4.0)

Built and validated the optional CUDA count backend, but do not promote it for
speed on this machine. Three paired complete 30-bootstrap measurements give
**49.563 s CPU vs 64.024 s CUDA**: CUDA takes **29.2% longer**.
It uses **20.3% less aggregate CPU time**, a resource tradeoff rather than a
latency win. Preserve v0.3.3 as the recommended optimized CPU executable; deliver
v0.4.0 CUDA separately as experimental opt-in.

## Scope and compatibility

The new optional `psmc-cuda` crate calculates transition counts on the GPU. Rust
retains input parsing, the original model, ordered forward/backward messages,
initial/emission counts, log-likelihood, full Q normalizer, Hooke–Jeeves and output.
Every GPU count cell uses the same ascending site additions and two separate
binary64 multiplications as C. Computational tiles carry accumulators and never
restart a statistical sequence. Full operation-order proof and FFI ownership
invariants are in [the crate README](../crates/psmc-cuda/README.md).

The backend is selected with `--backend cuda` in a `--features cuda` build. NVIDIA
libraries are loaded only when selected. CPU-only builds use no CUDA SDK, compiler,
headers or Rust package download. An existing NVRTC 12.9 runtime is reused here;
`nvcc` is absent. Runtime errors fail explicitly, with no concealed CPU fallback.

Hardware: RTX 5060 Ti, 16,311 MiB device memory, compute capability 12.0, driver
595.91.07; Intel i5-12600K, 16 allowed logical CPUs. The display and unrelated
applications share this machine. Rust 1.90.0, release opt-level 2, no LTO, one
codegen unit; NVRTC emits compute_75 PTX with FMA disabled and precise arithmetic.
See [environment provenance](../bench/cuda-environment.json).

## Experiments and discovered failure

A fresh isolated v0.3.3 profile attributes 3.142 CPU seconds of a 9.745-second
representative HG001 bootstrap fit to 64-state transition counts. This is a
profiling diagnostic, not a release timing. See [profile](../bench/cuda-profile.json).

The first hybrid prototype passed short unit cases, four ordered C snapshots and
a human fit, but the broader 30-bootstrap regression caught two mismatches
(synthetic replicates 24 and 26). The driver used pageable host uploads followed
by a nonblocking compute stream without establishing upload completion. The
corrected driver explicitly synchronizes the upload stream before launch. Both
failing fits pass three repetitions after repair; a concurrent large-transfer
regression was added. No tolerance was changed. See [original failure](../bench/cuda-validation.json),
[repair diagnostic](../bench/cuda-sync-diagnostic.json), and
[corrected regression](../bench/cuda-final-validation.json).

The original suite also contains a test asserting that CUDA is unavailable; it
is intentionally excluded for a CUDA-enabled build and replaced by CPU-build
rejection and missing-runtime/invalid-option tests. The independent exhaustive
path enumeration is retained from the unchanged scalar core, not repeated in this
GPU campaign. All four ordered C snapshots and every synthetic N30 bootstrap are
included in the new regression.

An isolated GPU-resident forward/backward prototype carries original boundaries
through 2048-site computational tiles. It exactly matches every CPU message and
scale on 257- and 50,001-site synthetic records. At the larger size its kernels
alone take 0.503 s versus 0.0364 s for CPU messages plus emission counts; allocation
and transfers increase it to 0.552 s. These single diagnostic runs reject this
one-block-per-record design before integration. They do not rule out every
possible batched GPU message design. Source and measurements are retained in
[the resident probe](../bench/cuda-resident-probe.json).

## Correctness evidence available before timing acceptance

The corrected CUDA build passes 113 selected C differential tests, including
all 30 full synthetic bootstrap fits (27 finite and the same three reference
pathologies). Four complete ordered snapshots compare 22,703 events and
39,142,084 finite numeric values exactly, including signed zero. NaN/Inf classes
are checked separately. All 35 existing release unit tests and five new CUDA
hardware/audit tests pass. A default workspace run passes 36 tests and explicitly
skips the four hardware-only tests; those four are included in the release run.

The CPU-only build succeeds with no CUDA SDK and with an invalid NVRTC path. Its
CPU fit succeeds; CUDA selection is rejected. Dynamic dependencies contain no
NVIDIA library. Physical execution on a host lacking an NVIDIA driver is not
separately tested.

## Operational boundaries

GPU buffers are bounded by tile size and the explicit CUDA buffer budget. For K64
and 16,384 sites the per-worker upper bound is 16,924,672 bytes. The budget excludes
CUDA context/module overhead and memory used by other applications. Worker
admission also observes the existing host-memory estimate. The CPU still retains
messages for each complete record; this implementation does not reduce that RAM.
Repeated records cache counts only within one exact model snapshot, and every
occurrence is added in input order. Snapshot mode disables the cache.

No ARM/NEON, other GPU, Windows/macOS, multi-GPU, whole-genome or user-owned input
has been validated. Public tests cover HG001 chromosome 22 and HG002 chromosome 1.
The prepared 30 HG002 bootstraps are not part of the throughput experiment.

## Reproduction and source changes

The campaign begins at source commit `0905ea0` (v0.3.3). The pinned vanilla source
is `82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`, built as recorded in the existing
reference manifests. New source files are `crates/psmc-cuda/{Cargo.toml,README.md,
src/lib.rs,src/driver.rs,src/counts.cu,src/tests.rs}`. CLI feature selection,
statistics and GPU-buffer admission extend `psmc-cli`; `psmc-core` adds counters;
`psmc-cpu` exposes a messages/initial/emission-count path without transition counts.
The dense oracle and original C implementation are retained. The synthetic
resident-message fixture generator and its CUDA/Python probe are diagnostic only.

Commands actually used (run from the repository; the local NVRTC path is in the
environment manifest):

```sh
python3 bench/cuda_profile.py
cargo test --workspace --offline
cargo test --workspace --release --all-features --offline -- --include-ignored --test-threads=1
cargo build --release --features cuda --offline
cargo build --release -p psmc-cli --no-default-features --offline --target-dir work/cuda/cpu-only-target
python3 bench/cuda_resident_probe.py
python3 bench/cuda_screen.py
python3 bench/phase1_differential.py --candidate work/cuda/wrapper \
  --raw work/cuda/final-gates --report bench/cuda-final-validation.json \
  --only '^(?!independent_path_enumeration_and_Q$|reject_cuda_backend$).+' --timeout 600
python3 bench/cuda_benchmark.py
```

The wrapper selects `--backend cuda` and the frozen `work/cuda/final-candidate`.
Exact per-run commands, hashes and raw paths are retained in JSON. Human inputs
and raw snapshots remain local/ignored; no genomes were uploaded. Benchmark
scripts use dedicated output directories and intentionally refuse to replace
existing bootstrap directories. Archive an earlier run before reproducing.


## Complete-workload decision

Each batch fits all 30 fixed HG001 chromosome 22 bootstrap draws (seeds
20261012..20261041), K64, N30, t15, r5, I0, with upstream 50,000-bin records and
all repeated/missing blocks retained. The same workload was already parallel
on the CPU. All 360 outputs across screening, warmups and measurement match the
retained hash-verified C outputs; every sampled index/proposal is independently
replayed. Of these outputs, 240 use CUDA and 120 use the CPU baseline.

| Complete batch | CPU v0.3.3, 16 workers | CUDA v0.4.0, 16 workers |
|---|---:|---:|
| Median elapsed seconds | 49.563 | 64.024 |
| Elapsed range seconds | 48.005–52.286 | 63.656–64.473 |
| Median aggregate CPU seconds | 650.06 | 517.96 |
| Median process peak RSS, KiB | 1,315,724 | 1,368,120 |
| Observed process GPU memory peak, MiB | 0 | 396 |

The GPU wins zero of three measured pairs. The predeclared promotion threshold
(>=5% median elapsed improvement and >=2 faster pairs, after exactness gates)
fails. All runs include CLI startup, NVRTC compilation, driver setup, transfers,
synchronization, CPU fitting and output. GPU memory is sampled every 0.5 seconds
and may miss brief peaks; driver/display activity and host contention are shared.
These ranges are descriptive, not a formal significance claim or prediction for
other machines. No 10x speedup is claimed.

CUDA worker screens: 2 workers 168.042 s; 4 workers 94.556 s; 8 workers 69.334 s;
16 workers 63.172 s. Select 16 before the fixed warmup plus three alternating
pairs. The screen is not included in the measured medians. A preliminary single
fit/tile screen is diagnostic only; it does not establish batch throughput.
See [complete benchmark](../bench/cuda-benchmark.json).

## Final additional gates and delivery

All 66 extended fixtures pass (39 finite,
27 with retained reference pathologies).
Full unsplit HG001 and HG002 K64/N30 fits are finite and exactly match C outside
the single version line. Single descriptive CUDA validation times are
14.511 s and 63.518 s;
these are not repeated performance estimates. HG002 contains 2,489,565 bins and
uses 2,624,252 KiB peak host RSS. Neither human check creates
new HMM boundaries to fit the GPU tile budget.

Seven error controls and two scheduler controls pass. They cover missing NVRTC,
invalid/oversized tiles, zero/insufficient device budget, unsupported state count,
CPU-build CUDA rejection, constrained worker admission and reversed task order.
Eight identical fits agree across four workers and two budget-admitted workers.
No GPU fallback occurs. See [delivery checks](../bench/cuda-delivery.json).

Final commands also include `python3 bench/cuda_delivery.py`,
`cargo fmt --all --check`, a locked/offline CUDA rebuild, and
`python3 bench/cuda_audit.py`. The audit rechecks all 360 batch outputs, 66 extended
outputs, two human outputs, published/frozen binary identities and baseline
preservation. The earlier wrapper was updated between attempts; its exact
original contents are retained at `work/cuda/initial-wrapper` with the original
recorded hash. Failed reports remain unchanged.

Published CUDA executable: `bin/psmc-rs-cuda`, SHA-256
`60c1499386096d7c5412c822ab8cf635af716ffc1399804f7dc3bb05b893f15c`.
Preserved CPU executable: `bin/psmc-rs` and `bin/psmc-rs-v0.3.3`, SHA-256
`f0c3282e87e3eed0cc31c63a438429c19ad47cedec4c56c1150cc8520838e305`.
Source/configuration/report hashes are in [the final audit](../bench/cuda-audit.json).
All code, derivation, tests and results are committed together from base 0905ea0.

The next GPU milestone, if pursued, should test pinned asynchronous transfers,
CPU/GPU overlap and a scheduler that batches independent records across fits.
The rejected one-record GPU message design is not a suitable default. Preserve
strict arithmetic and repeat the complete-workload gate before any promotion.
Data-center FP64 hardware and whole-genome/user inputs remain untested; lower
precision or a different inference method requires a separate numerical contract.
