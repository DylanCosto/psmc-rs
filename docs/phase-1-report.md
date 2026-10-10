# Phase 1 — Rust dense scalar PSMC

The Rust oracle is implemented and passes the supported synthetic compatibility
gate on the tested Linux stack. All **115 differential checks pass**, including
all 30 full-length bootstrap fits. The literal Rust implementation is currently
**slower than vanilla C** on both measured fixtures. No acceleration, production
throughput, biological validity, or GPU claim is established.

## Implementation and build

The workspace contains three crates: `psmc-core` for model/HMM/counts/optimizer/EM
and RNG, `psmc-io` for parsing and ordered bootstrapping, and `psmc-cli` for fitting,
legacy records, decoding, and diagnostic snapshots. All inference is Rust code.
The only FFI boundaries are scalar system log/exp, printf-compatible numeric
formatting, and owned gzip input. The original MIT notices remain in the source
and `reference/LICENSE.psmc.txt`.

Reference: `lh3/psmc` commit `82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`,
GCC 13.3, upstream O2, floating-point contraction disabled. Rust: 1.90.0,
edition 2024, release optimization level 2, LTO off, one codegen unit, no registry
dependencies. Tested host: Intel i5-12600K, x86-64 Ubuntu 24.04, glibc 2.39.
Both implementations use the same hashed system libm. Rust uses system zlib 1.3.
Compiler/LLVM versions, source hashes, library hashes, lockfile, commands and
machine configuration are in [the build record](../bench/phase-1-build.json).

The delivered `bin/psmc-rs` SHA-256 is
`e112ed9a8d7d98cc5e29f497e8567e1de96f3e0210a0cb324a79dc91c5e65dd0`.
Final differential tests used an immutable copy of that executable; benchmark,
conversion, and CLI-review evidence identify the same digest.

## Correctness evidence

| Check | Result |
|---|---|
| Rust unit tests | 17 pass in debug and 17 in release; formatting check passes |
| Isolated model construction | 60 cases; 64,446 binary64 values byte-exact |
| Isolated Hooke–Jeeves optimizer | 16 scenarios; 5,962 callback/final binary64 values byte-exact |
| End-to-end differential suite | 115/115 pass, zero failures |
| Complete internal snapshots | Five pairs, 122,725 ordered events, 42,642,569 finite numeric fields exact |
| Snapshot nonfinite values | 1,693 NaNs and 9 infinities classified identically; not counted as finite values |
| Complete bootstrap trajectories | All 30 match through all 30 iterations; 27 finite and 3 reference pathologies |
| Independent CLI/I/O review | 11 targeted controls pass |
| Comparator negative controls | Four tests reject numeric changes, omitted callbacks, metadata over-filtering and nonfinite-class changes |
| Upstream conversion | `psmc2history.pl` history and `psmc_plot.pl` data/parameter files byte-identical |
| Rendered plots / Clippy | `not_run`: gnuplot / pinned Clippy component unavailable |

“Exact” output comparison excludes **only** the single `MM Version` line. All
other bytes remain, including numerical `MM` fields and optimizer evaluation
counts. Internal comparisons use zero tolerance and check signed zero, event
order, matrix cells, scaled messages, complete counts, normalizer, callback
parameters, and EM results. The independent path-enumeration diagnostic retains
its previously declared tolerance; it does not relax the C-versus-Rust gate.

The suite covers aliases, plain/gzip/stdin/FASTQ input, independent boundaries,
missing data, repeated records, supplied parameters and explicit time grids,
divergence, 23/64-state patterns, random replay, decoding/capping, unsupported
flags, malformed input and output failure handling. Nonfinite optimizer trials
can occur inside a fit with finite printed results; snapshot classification
preserves these trials rather than deleting them.

The three full-bootstrap pathologies are exactly the previously observed C cases:
replicate 16 first prints nonfinite QD at round 28; replicate 26 first prints
nonfinite LK at round 26; replicate 28 first prints nonfinite RI at round 23.
Matching these outputs verifies reproduction, not scientific usability. Runtime
warnings check model arrays and core fit statistics; they are not a complete
finite-output validator. In particular, replicate 28's RI-only NaNs do not
trigger that warning. The harness checks all numerical records and distinguishes
these cases from the 27 finite trajectories. No reference pathology was repaired
or hidden to make the port pass.

Evidence: [differential suite](../bench/phase1-differential.json),
[isolated comparisons](../bench/phase-1-isolated/results.json),
[Cargo checks](../bench/phase1-cargo-checks.json),
[review](phase-1-review.md),
[harness controls](../bench/phase1-harness-selftest.json), and
[output conversion](../bench/phase1-output-tools.json).

## Measured time and memory

Uninstrumented binaries ran sequentially on identical inputs/options. Each case
had one warmup per implementation followed by three measured pairs with
alternating order. Wall time includes process startup and output; memory is
Linux maximum RSS. Every warmup and measured output was finite except the usual
initial RI infinity and matched exactly after the version exclusion.

| Synthetic fixture | Vanilla median wall | Rust median wall | Vanilla median peak RSS | Rust median peak RSS |
|---|---:|---:|---:|---:|
| 13,200 bins, 23 states, 30 iterations | 0.383 s | 0.485 s | 4,744 KiB | 5,128 KiB |
| 52,800 bins, 64 states, 5 iterations | 1.563 s | 2.072 s | 27,228 KiB | 26,496 KiB |

Rust takes about 1.26× and 1.33× the C wall time in these small tests. This is a
correctness baseline, not an optimized release. The five-iteration 64-state
case is a partial trajectory. Three runs on a shared host do not establish a
portable performance distribution. No test job or archive compression ran
concurrently with these measurements; unrelated host activity was not isolated.
[Raw timing records, commands and variability](../bench/phase-1-benchmark.json)
are retained.

## Changes, execution and remaining scope

Added the Cargo workspace/toolchain/lockfile; three Rust crates; source-backed
math and validation contracts; isolated, integrated, negative-control, conversion
and benchmark runners; a release binary; and updated project documentation.
The supplied original documents remain context and their historical checkboxes
are not treated as fresh validation. Previously missing math/validation files
were replaced explicitly, not represented as recovered attachments.

Commands actually executed include `cargo fmt --all --check`, debug and release
`cargo test --workspace --locked --offline`, release builds,
`bench/check_phase1_isolated.py`, the complete `bench/phase1_differential.py`
suite against the immutable final binary, harness unittest discovery,
`bench/phase1_output_tools.py`, `bench/phase1_build.py`, and
`bench/phase1_benchmark.py --run`. Exact arguments and outcomes are in their
linked machine-readable reports. The original Perl scripts generated identical
plot data, but their zero exit code does not certify rendering: gnuplot was absent.

Early checks were interrupted as CLI safety fixes landed. One shared-release
rebuild invalidated a concurrent run: 58 cases had passed and 54 were blocked by
the executable-hash guard. This was not counted as a compatibility pass or
concealed as a numerical failure. The final immutable run reran all 115 cases
successfully. Superseded reports retain provenance and raw-file relocation
manifests; their large raw files remain under excluded `work/`.

Supported flags and deliberate safety exclusions are in the [README](../README.md).
The core preserves scalar arithmetic order and legacy quirks. Malformed input,
unsafe supplied-grid/divergence combinations and output aliases are rejected.
Writes are not yet atomic; no checkpoint/resume or memory-budgeted scheduler is
implemented. Large genomes and very large state counts are untested.

The next milestone is CPU memory/workspace engineering and deterministic
bootstrap scheduling, with this dense oracle retained. Real-workload benchmarking
still needs the exact input, preprocessing/splitting, command/settings and worker
budget. The user's 30 bootstraps already run in parallel. Cross-platform parity,
optimized CPU, legacy CUDA, real-genome inference, and the 10× target remain
`not_run` or unproven. No Phase 2/3 optimization or CUDA kernel was added here.

## Deliverables and reproducibility

The project folder retains source, the runnable Linux binary, fixture manifests,
raw numerical output, complete compressed snapshots, and reports. The compact
`psmc-rust-phase-1.zip` contains source, binary, test fixtures, reports, raw ordinary
outputs and checksums. It omits rebuildable `work/`/`target/`, superseded raw runs,
and the 847,857,352 bytes of final compressed snapshots. Those ten full snapshots
remain in the local project; their hashes and reproduction command are in
[the snapshot manifest](../bench/phase1-snapshot-manifest.json).
The package manifest lists exclusions. No events were truncated during comparison.
The original Phase 0 archive is preserved separately.
