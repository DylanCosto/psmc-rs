# PSMC-rs

A local Rust implementation of PSMC's demographic model and Hooke–Jeeves
optimizer, with CPU acceleration and deterministic parallel record processing.
Accepts existing `.psmcfa` inputs. **Strict mode is the default; equivalent mode
is an explicit experimental choice.**

## Build and run

Rust 1.90.0 is pinned. The CPU build has no Cargo registry dependencies and uses
system libm, libc and zlib. The tested platform is x86-64 Linux/glibc 2.39.

```bash
cargo build --release --locked --offline
./target/release/psmc-rs -p '4+25*2+4+6' -N 30 -t 15 -r 5 -I 0 \
  -o result.psmc input.psmcfa
```

Plain or gzip FASTA/FASTQ input is accepted; `-` reads stdin for a single fit.
The original T/K/N encoding and supported aliases are retained. Each record is
an independent HMM sequence. Missing bins still carry transitions.

Single CPU fits automatically use the available CPU count to process independent
records. `--record-workers 1` limits a fit to one worker; set another positive
count to cap it. An unsplit single record cannot gain record parallelism.
Strict mode admits record workers against a memory estimate: by default, half of
available memory (including detected cgroup headroom). Use `--memory-mib MIB`
for an explicit budget, including when requesting workers manually. Admission
reserves the largest record's message capacity for each worker, including idle
retained buffers, the fit owner, queued inputs, counts and optional decoding.
The chosen worker count and estimate appear on stderr and in `--stats`.
A budget too small for one record fails before opening output files. Input
loading happens first; this is a conservative estimate, **not an OS RSS hard
limit** or protection from other processes consuming memory later. When memory
availability cannot be detected, the default is 1024 MiB. Equivalent single fits
keep their full worker default; single-fit `--memory-mib` applies to strict CPU
fits. Bootstrap uses its separate existing admission budget. When launching multiple
fit processes yourself, divide memory budgets between them or use the bootstrap
runner; per-process admission does not reserve RAM globally.
Dense, CUDA and snapshot fits retain their own execution policy; automatic record
workers do not apply to them. Strict CPU snapshots still receive memory admission.
See [memory admission results](docs/strict-memory-admission.md).

To opt into the faster equivalent arithmetic:

```bash
./target/release/psmc-rs --mode equivalent -p '4+25*2+4+6' -N 30 \
  -t 15 -r 5 -I 0 -o equivalent.psmc input.psmcfa
```

## Guarantees and mode choice

| | Strict (default) | Equivalent (opt-in, CPU only) |
|---|---|---|
| Model, optimizer, iterations, f64 precision | Original PSMC | Same |
| Arithmetic | Preserves tested C operation order | Structured scans and triangle margins; different rounding and optimizer paths |
| Objective diagnostic | Original `QD`, full entropy normalizer | `QU`, unnormalized Q; compare before/after only within one round |
| Evidence | Exact pinned-C output and internal-trace checks on the tested stack | Component checks, C-calibrated HG001/HG002 panels, and a prospective 200 Mb known-truth panel |
| Snapshots | Supported for testing | Rejected |

Strict output equality excludes only the honest `MM Version` line. This is a
claim about the pinned build and tested inputs, not universal bitwise equality
across machines, compilers or libm versions. Scheduling keeps reductions in input
order in both modes; changing worker counts does not change fitted output.

Equivalent mode's checkpoint boundaries retain HMM messages and add no sequence
boundaries. Invalid structured candidates use the documented literal fallback.
`QU` changes a diagnostic contract; it is not interchangeable with C's `QD`.
The [linear-mode report](docs/linear-equivalent-report.md) describes the numerical
gates and ridge diagnostic. The [known-truth protocol](docs/known-truth-protocol.md)
sets the separate simulation assessment; the [qualification report](docs/qualification-report.md)
records its results and unresolved outliers. The subsequent
[200 Mb panel](docs/known-truth-200mb-report.md) passes all prospectively declared
primary-band and event checks across 30 datasets, with strict/C exactness on all
fits. These panels do not establish accuracy for every demographic history or
qualify the user's unavailable whole-genome workflow.

## Run independent bootstraps

Supply blocks already split by your established preprocessing procedure. This
runner does not split input or introduce new HMM boundaries.

```bash
./target/release/psmc-rs bootstrap --mode strict --replicates 30 \
  --workers 16 --memory-mib 16384 --seed 20261009 \
  --output-dir bootstrap-results -p '4+25*2+4+6' -N 30 -t 15 -r 5 -I 0 \
  blocks.psmcfa
```

The output directory must be new. Defaults are 30 replicates, available CPU
workers, a 2048 MiB admission estimate and `--scheduler shared`. Fits and record
helpers share one admitted worker budget. `--scheduler fit` selects fit-only
scheduling. Do not combine bootstrap with `--record-workers`; use `--workers`.
On Linux, hybrid PMU CPU lists identify P/E cores within inherited affinity;
when unavailable, a >=85% maximum-frequency heuristic avoids treating only the
highest-boost preferred cores as fit owners. Unknown topology stays unpinned.

The memory estimate can reduce worker admission; it is **not an OS-enforced RSS
limit**. Input loading precedes admission. The manifest reports requested/admitted
workers, scheduling, affinities, estimated memory, seeds, draws and failures.
Full-genome memory and termination recovery remain unqualified.

Replicate i uses seed `base + i`, original ordered bootstrap draws and the original
initialization RNG stream. Duplicate records retain their multiplicity and
original reduction order even when cached. Each fit writes its `.psmc`,
`.stats.json` and `.draws.jsonl`; `manifest.json` summarizes the batch.
Failures retain partial files, let other fits finish and cause a failing exit.
Atomic resume is not implemented.

## Useful controls

Run `--help` for the complete supported list.

| Option | Purpose |
|---|---|
| `-p -N -t -r -l -I` | Pattern, iterations, maximum time, theta/rho, grid alpha, initialization |
| `-i -o` | Supplied parameter file and output path |
| `-b --seed INTEGER` | One legacy ordered-record bootstrap and reproducible RNG seed |
| `-d -D -s -C` | Posterior segments, full posterior, scales and transition cap |
| `-T` | Legacy divergence parameter, subject to supplied-file checks |
| `--backend cpu\|dense` | Optimized CPU (default) or retained scalar oracle |
| `--simd auto\|off\|avx` | Runtime AVX dispatch, generic path or require AVX |
| `--cache on\|off` | Repeated-record cache within one exact parameter snapshot |
| `--stats FILE` | Single-fit counters and instrumented E/M timers |
| `--snapshot FILE` | Large test-only messages, counts and optimizer traces |

Snapshot execution bypasses record sharing and count-only caching so every
occurrence's messages can be inspected. Do not use snapshots or instrumented
phase timings for throughput claims. Batch phase timing is disabled; counters
remain active. `PSMC_SEED`, `PSMC_SNAPSHOT`, `PSMC_BOOTSTRAP_TRACE` are supported
harness controls; unset them for ordinary benchmark runs.

The original `-c` and `-S` are rejected (`-S` is not a seed option). VCF/long-read
conversion, checkpoint/resume and new plotting commands are not implemented.
Parameter files contain the raw PA payload, without its `PA` prefix. An explicit
time grid cannot also supply divergence; ordinary supplied parameters with `-T`
must include their own trailing divergence.

Some inputs make vanilla PSMC produce NaN/Inf. Rust preserves reference behavior
and warns on nonfinite fit records. A successful exit does not certify finite
inference; the expected round-zero `RI inf` is treated separately. Malformed input,
unsafe parameter combinations, path aliases and all-missing input without explicit
initial parameters are rejected. Streaming output writes are not atomic.

## Performance and evidence

On the tested i5-12600K, v0.6.1's HG001 30-bootstrap medians were **9.48 seconds
in equivalent mode** and **44.02 seconds in strict mode**, with 16 workers and
the report's exact input/configuration. The linear E-step milestone was 3.10x
faster than v0.5.1 equivalent mode in its separate paired benchmark. These are
workload-specific measurements; do not extrapolate them to an untested genome.

- [Shared-record tests and measured timings](docs/shared-record-results.md)
- [Linear equivalent validation and timings](docs/linear-equivalent-report.md)
- [Mathematical contract](MATH_AND_COMPATIBILITY.md) and [validation policy](VALIDATION_AND_BENCHMARKS.md)
- [Pinned original C source](https://github.com/lh3/psmc/tree/82fa2ada83ee463fe1251b562ae3d60e82d7ad6a)
- [Historical optimization campaign](docs/optimization-exhaustion.md) and [execution history](EXECPLAN.md)

The optional [CUDA backend](crates/psmc-cuda/README.md) requires a separate Cargo
feature and explicit selection. It was slower than CPU in the measured campaign;
CPU remains recommended. ARM/NEON, non-Linux platforms and other CPU families
have not passed hardware qualification. Topology policy fixtures are not tests
on actual AMD or other Intel machines.

## Test and reproduce

```bash
cargo fmt --all -- --check
cargo test --workspace --release --locked --offline
python3 -m unittest discover -s bench -p test_known_truth.py
```

The [CI workflow](.github/workflows/strict.yml) builds pinned vanilla C, checks
committed golden outputs and runs Rust tests. Hosted execution requires a remote.
The [reference build instructions](README_PHASE0.md) and scripts in `bench/`
retain source hashes, commands and evidence. Historical runners belong to their
recorded source versions; do not overwrite old reports with new executions.
Large ignored evidence is stored in a [separate local archive](docs/evidence-archive.md) with per-file
checksums and restoration instructions. Compact reports, protocols, source,
fixtures and reproduction scripts stay in Git.

The workspace separates the dense model/oracle (`psmc-core`), CPU engines
(`psmc-cpu`), input/bootstrap handling (`psmc-io`) and CLI (`psmc-cli`). Inference
does not call C PSMC. Original MIT notices remain in translated sources and
[LICENSE.psmc.txt](reference/LICENSE.psmc.txt).
