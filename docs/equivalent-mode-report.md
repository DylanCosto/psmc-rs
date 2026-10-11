# Structured CPU mode: implementation and validation

**Follow-up:** [the numerical review and SIMD experiment](equivalent-followup.md)
reproduce the user’s distribution summaries and investigate the weakly identified
HG001 interval. The gates below are historical engineering screens, not a
calibrated scientific test: vanilla C itself fails the fixed curve screen on
four HG001 fits. Their failure alone is not evidence of a structured-code defect.

Version 0.5.0 adds `--mode equivalent` as an opt-in experimental CPU mode.
Strict mode remains the numerical default. The structured arithmetic passes its
component checks, but it **does not meet the proposed full-fit equivalence gates**.
Four HG001 bootstrap curves exceed the predeclared 0.01-log-unit screen. The
largest difference is in an early interval with a very large estimated lambda;
theta, rho and reported likelihood remain close. This evidence does not establish
scientific interchangeability, nor does it prove that either fit is biologically
more accurate.

The user's CPU-default, dynamic-version and pinned-C golden-test changes are
preserved. The implementation retains the model, original Hooke–Jeeves optimizer,
30 fitting iterations, full transition counts, Q entropy normalizer, record
boundaries, missing-data behavior and repeated-block multiplicity. Strict output
compatibility remains exact on the tested Linux/glibc stack.

## What changed

`psmc-core/src/structured.rs` computes triangular factors and evaluates candidate
Q from count margins. `psmc-cpu/src/equivalent.rs` owns factors, guarded literal
fallbacks and per-snapshot caching. Forward/backward use prefix/suffix scans in
the existing CPU workspace; the original ordered kernels remain the strict path.
The CLI, output header, statistics and batch manifest identify the selected mode.
Matrices are materialized for counts and round output, and for diagnostic observers.
The experimental CLI initially rejects snapshots and dense/CUDA combinations.

Forward/backward and eligible candidate model/Q evaluations are linear in state
count. **Transition counting remains quadratic**, because triangular margins do
not determine the full legacy Q entropy normalizer. The algebra, counterexample
for entropy reconstruction, eligibility checks and predeclared thresholds are in
[the numerical contract](equivalent-mode.md). No reduced precision or fast-math is
used in Rust, and there is no claim of a fully linear E-step or a 10x speedup.

## Numerical evidence

The human panel contains each original chromosome input and 30 paired bootstrap
samples: HG001/NA12878 chr22 (508,185 bins) and HG002 chr1 (2,489,565 bins). These
are the existing public, documented PSMC inputs, not whole genomes or a private
user dataset. The same 50,000-bin splitting procedure, retained remainders and
fixed bootstrap draws are used across implementations.

Two unmodified C builds at reference commit
`82fa2ada83ee463fe1251b562ae3d60e82d7ad6a` complete all 62 fits each:
GCC O2 with contraction disabled, and GCC O2 with native instructions and
contraction enabled. Disassembly finds zero versus 15 FMA-family instructions.
The additional O0 diagnostic was stopped before completing its first fit; its
partial output is retained and excluded. This uses the user's two-build option;
no fit sizes, replicate counts or numerical tolerances were relaxed.

| Across original + 30 bootstraps | HG001 | HG002 |
| --- | ---: | ---: |
| Strict Rust outputs matching standard C | 31/31 | 31/31 |
| Maximum structured/strict curve difference, log lambda | 0.251957 | 0.001057 |
| Maximum C-build curve difference, log lambda | 0.080979 | 0.000343 |
| Fits passing all exploratory numerical screens | 27/31 | 31/31 |
| Fits within every selected compiler-range limit | 7/31 | 6/31 |
| Fits below 1% of pointwise bootstrap log-curve SD | 28/31 | 31/31 |
| Largest structured difference as a fraction of bootstrap SD | 5.18% | 0.0694% |

HG001 bootstrap indices 3, 13, 26 and 28 fail the curve screen. In index 13, the
first grouped lambda changes from about 845,981 to 657,562 (a 22.3% reduction).
Its structured curve shift is 0.252 log units, compared with 0.00369 between the
two C builds for that same sample. The maximum theta/rho relative differences
across the HG001 panel are 0.0156%/0.0156%, and the maximum absolute reported
likelihood difference is 0.000247. On HG002 those maxima are
0.00230%/0.00237% and 0.000169.

The original, unsampled fits are much closer: maximum curve differences are
1.55e-5 (HG001) and 7.61e-5 (HG002) log units. The small same-model errors therefore
must not be used to promise equally small changes in every fitted parameter.
Compiler variation is empirical sensitivity, not a scientific error bound.

Comparisons use nine-decimal PA parameters, six-decimal RS times and LK
likelihoods. Curves are evaluated on a fixed 256-point logarithmic time grid from
the standard C original fit; interval-index differences are also retained.
The printed likelihood precedes the last M-step, as in vanilla PSMC. Zero printed
difference is resolution-limited. Full per-fit values and all gate failures are
in [equivalent-analysis.json](../bench/equivalent-analysis.json).

Component and strict evidence:

- 45 tests pass in both debug and release; four hardware CUDA tests are explicitly
  not run for this CPU milestone. All-features compilation also passes.
- Same-parameter tests cover 2–64 states, masks, record boundaries, short sequences,
  explicit grids, divergence, invalid candidates, underflow eligibility, cache
  multiplicity and a 300-candidate parameter sweep.
- A further 186 printed human-fit parameter snapshots, including the sensitive
  replicate, pass the declared component tolerances on a synthetic 2,048-bin
  sequence. Maximum relative errors: transition 3.75e-16, forward 3.83e-14,
  backward 1.02e-13, counts 9.51e-14 and normalized Q 2.22e-13.
- The strict regression passes 338 applicable checks and ten exact internal
  traces, preserving the original 27 finite / three pathological synthetic
  bootstrap classifications on dense, automatic CPU and scalar CPU backends.
  The unchanged historical runner reports two failures because it still expects
  equivalent mode to be unavailable on CPU; those obsolete availability checks
  are identified separately in the audit. New mode-selection tests pass.
- All 62 strict human outputs match C bytes except the version line. All 124 Rust
  human fits complete without nonfinite output. Twenty-four additional fits
  verify deterministic scheduling and cache controls for equivalent mode.
- The 60 equivalent bootstraps use literal model/Q fallback on 3,947 of 7,032,646
  model updates (about 0.056%). These are guarded model updates, not fit failures.

## Performance

One warmup per mode followed by three alternating measured pairs, each with
30 HG001 bootstraps and 16 workers, passes the predeclared performance gate:

| Median of three measured batches | Strict CPU | Equivalent CPU |
| --- | ---: | ---: |
| Elapsed seconds | 45.2498 | 32.7541 |
| Aggregate CPU seconds | 614.25 | 429.85 |
| Peak RSS, KiB | 1,315,144 | 1,309,132 |

Equivalent mode is **1.3815x faster**, uses **27.6% less elapsed time** and
**30.0% less CPU time**, and wins all three pairs. Measured elapsed ranges are
45.07–45.48 seconds for strict and 32.01–34.14 seconds for equivalent. Memory is
approximately 1.25 GiB for both; the small observed RSS difference is not claimed
as a memory optimization. All 240 warmup/measured outputs and bootstrap draws
reproduce their respective validated mode exactly.

Additional v0.4.1 CPU controls take 43.97 and 47.30 seconds, overlapping the new
strict timings. The new strict median is 0.84% below their mean; this two-run
control does not establish a speed change. Their 60 outputs match strict exactly.
The host is shared, and the benchmark covers this HG001 workload on this CPU.
These results compare equivalent with the current strict CPU implementation,
not with vanilla C. Concurrent correctness runs are not performance evidence.
The numerical qualification gate remains failed despite the speed gate passing.

See [the complete timing evidence](../bench/equivalent-performance.json).

## Provenance and reproduction

Installed CPU executables are `bin/psmc-rs` and `bin/psmc-rs-v0.5.0`. Both default
to strict mode and the CPU backend. The v0.4.1 CPU executable and optional CUDA
executable are preserved. [The installation manifest](../bench/equivalent-install.json)
and [final audit](../bench/equivalent-audit.json) pin the exact artifacts.

A [CI workflow](../.github/workflows/strict.yml) checks out the pinned C reference,
compiles it with GCC 13 and contraction disabled, checks four live-C cases against
the saved golden files, then runs Rust's full release tests (including 16 golden
backend combinations). The local live-C checks pass. Hosted CI is **not_run**:
this local repository has no remote configured. The checkout action is pinned to
an immutable commit verified against the [official action repository](https://github.com/actions/checkout).

The source baseline is `f86333f` plus the user's edits. Release uses Rust 1.90,
opt-level 2, one codegen unit and no LTO. The machine is an Intel i5-12600K with
16 logical CPUs on Linux/glibc 2.39. Hashes, compiler commands, inputs, sampled
records, outputs and source files are retained in the `bench/equivalent-*.json`
reports; raw evidence and the tested executables are under `work/equivalent/`.

Commands executed include:

```bash
cargo test --locked --offline --workspace
cargo test --release --locked --offline --workspace
cargo check --locked --offline --workspace --all-features
cargo build --release --locked --offline --bins --examples
taskset -c 0 python3 bench/phase3_validate.py --run \
  --candidate target/release/psmc-rs --report bench/equivalent-strict-regression.json
python3 bench/equivalent_c_baseline.py
python3 bench/equivalent_c_resume.py
python3 bench/equivalent_validate.py
python3 bench/equivalent_analysis.py
python3 bench/equivalent_benchmark.py
python3 bench/ci_strict_reference.py --reference work/equivalent/c-baseline/o2
python3 bench/equivalent_audit.py
```

The C build initially lacked the zlib header path; existing local headers and the
system runtime resolved it without installing packages. The first strict-runner
invocation exited before testing because it requires CPU pinning, then ran pinned.
Both events and the O0 interruption are retained. The first performance attempt
stopped during warmup because objcopy's section-dump invocation rewrote its input
ELF. The binary hash guard caught it before any measured pair. The machine-code
sections matched; the tested archive was restored from the strict-regression
freeze, the target was rebuilt, and the verifier now uses a separate output ELF.
The original attempt is retained in `bench/equivalent-repairs.json`; the fixed
protocol restarts without changing thresholds. The resume runner continues this
specific C campaign; the baseline runner now reproduces the selected two-build
panel from a fresh output directory. Runners refuse to overwrite their raw evidence.
The final rebuild is checked against the validated executable's machine-code
section after test/documentation-only additions.

ARM/NEON, other toolchains/libm versions, new GPU hardware runs, private inputs and
whole genomes are not validated here. A future production-equivalence decision
needs independently justified scientific tolerances and broader data validation.
Strict mode remains available for exact reproduction; the experimental mode is
available for investigating the speed/trajectory tradeoff.
