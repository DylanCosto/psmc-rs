# Optional strict CUDA count backend

Derivation: for each source/destination (k,l), C initializes A[k,l]=1e-25,
then visits sites u=1..L-1 and performs A += (f[u,k]*ae[obs[u+1],k,l])*b[u+1,l].
Different cells have no data dependencies. One CUDA thread owns one cell; both
multiplications and the addition explicitly use round-to-nearest binary64
intrinsics. NVRTC additionally disables contraction and fast math. Site tiles
carry the previous A value without resetting or forming partial sums. Missing
symbols still participate; the last site omission is unchanged. No atomics,
horizontal reductions or sequence boundaries are introduced.

The CPU computes messages, likelihood (same system libm), initial/emission counts,
model and optimizer. ae is computed by Rust in the original order. Observation
content caching is restricted to one immutable model/expectation call; each
occurrence is still aggregated in input order. Snapshot mode bypasses this cache.

This is intentionally a hybrid feasibility backend, not a claim of fully GPU
resident PSMC. The stage gate determines whether further porting is warranted.

## Build and use

```sh
cargo build --release --locked --offline -p psmc-cli --features cuda
# Only needed when NVRTC is not in the system loader search path:
export PSMC_NVRTC_LIBRARY=/path/to/libnvrtc.so.12
target/release/psmc-rs --backend cuda --seed 42 -N 30 input.psmcfa
```

No downloaded Rust crates, CUDA headers or nvcc are required. The runtime requires
Linux, NVIDIA libcuda.so.1, and NVRTC with compute_75 PTX support. Tested versions
and hardware are recorded in bench/cuda-environment.json and the milestone report.
Other platforms/devices are not validated. Without `--features cuda`, the CLI
rejects CUDA selection before fitting. CPU builds need neither driver nor NVRTC.
Default backend selection is unchanged; CUDA must be explicitly requested.

`--cuda-tile-sites` controls computational transfer tiles (default 16384, range
1..1048576). State count is limited to 1..1024. `--cuda-memory-mib` (default 1024)
is a bound on explicitly allocated device buffers across bootstrap workers; it
excludes driver/context/module overhead and other applications. Per worker the
upper bound is `16*tile_sites*states + tile_sites + 32*states*states` bytes.
Bootstrap admission takes the minimum of requested workers, CPU availability,
host-memory admission and this device-buffer budget. An allocation/runtime error
fails the fit explicitly; no CPU fallback is concealed. Host message storage is
still proportional to the longest original record. Tiles do not reduce that RAM.

Device libraries, context, module, stream and flat buffers are owned by the
thread-bound driver object. It cannot be sent/shared between Rust threads. Each
worker has its own module, stream and buffers within a retained primary context.
The PTX compilation result is immutable and shared once per process. Buffer
copies validate shapes, use live Rust slices, and finish before results are read.
Pageable synchronous host-to-device uploads can return before DMA completes;
an explicit default-stream completion precedes the nonblocking compute launch.
This dependency is covered by the concurrent large-transfer test and full fits.
No generalized raw-pointer CUDA API is exported by the crate.

The `--stats` output records CUDA launches, uploaded/downloaded bytes, count-stage
wall seconds for the tile upload/kernel/download loop (when profiling is enabled;
excludes runtime initialization and per-model ae upload), and zero fallback count. Bootstrap
statistics always include operation counters; timed profiling remains disabled
there. The manifest records buffer budget, per-worker bound and admitted workers.

## Tests and audit

```sh
cargo test --workspace --locked --offline
# These ignored tests actually require hardware; skipping them is not a GPU pass.
cargo test -p psmc-cuda --release --locked --offline -- --include-ignored --test-threads=1
```

The hardware suite checks bit equality (including signed zero), NaN/Inf classes,
state tails, tile carry, missing data, cache multiplicity/invalidation, changing
models, pageable transfers and nonfused PTX. Full CLI/C snapshot and fit evidence
is separate. Older failed attempts remain in the milestone artifacts.

Sources: NVIDIA [NVRTC 12.9](https://docs.nvidia.com/cuda/archive/12.9.1/nvrtc/index.html)
and [API synchronization behavior](https://docs.nvidia.com/cuda/archive/12.9.1/cuda-runtime-api/api-sync-behavior.html).
