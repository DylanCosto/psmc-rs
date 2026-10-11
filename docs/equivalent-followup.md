# Structured-mode review and lockstep experiment

This follows the v0.5.0 milestone at commit `f191674`. Its historical measurements
and failed engineering gates remain intact. This follow-up distinguishes those
screens from evidence of an implementation error.

## Numerical interpretation

The user's calculations reproduce exactly from the saved per-fit evidence:

| Original chromosome + 30 bootstraps | HG001 | HG002 |
| --- | ---: | ---: |
| Median maximum log-curve difference, structured/strict | 5.45195e-5 | 4.47583e-5 |
| Median maximum log-curve difference, C-FMA/C-O2 | 1.05422e-4 | 4.03338e-5 |
| Structured difference exceeds C-build difference | 11/31 | 17/31 |
| C-build comparisons exceeding 0.01 | 4/31 | 0/31 |

C fails the 0.01 screen on HG001 indices 3, 5, 26 and 28. Structured fails on
3, 13, 26 and 28. A threshold that rejects the reference's own arithmetic
variation does not specifically diagnose a structured-code defect. Nor is one
pair of C builds a calibrated per-fit envelope: the perturbations are
correlated deterministic computations, not independent draws with a known
50% failure probability. Requiring multiple such bounds jointly further
reduces the reported pass rate.

The central distributions are similar, with a structured tail outlier. Thirty
bootstrap replicates and two compiler builds do not establish distributional
equivalence. These already-inspected data should inform a new prospective
contract, not supply a retrospectively chosen passing threshold. Bootstrap
spread remains useful context: the largest deviation is 5.18% of the pointwise
log-curve SD. That SD is not itself a simultaneous confidence band or a bound
on implementation bias.

### Bootstrap 13: common objective diagnostic

Re-evaluated the two printed final parameter vectors on their exact 500,000-bin
sample using the strict CPU oracle. Each count matrix includes all repeated
record occurrences. Q comparisons use the **same frozen expected counts** for
both candidate vectors; comparing each fit's own printed QD would compare two
different auxiliary objectives.

- Fresh observed log-likelihood: strict -122983.812118454662; structured
  -122983.812384808989. Difference: -0.000266354327.
- Structured-minus-strict Q on strict endpoint counts: -0.000182582793.
- The same comparison on structured endpoint counts: -0.000174494809.
- Holding every other parameter fixed, nine logarithmically spaced first-group
  lambda values from 845981 to 657562 change likelihood by at most 2.59e-6 on
  the strict slice and 1.12e-6 on the structured slice.

This supports a very flat, weakly identified direction as the explanation for
the large relative lambda shift. The complete parameter-vector Q differences
are slightly above the suggested 1e-4. This is a conditional slice, not a profile
likelihood: nuisance parameters were not reoptimized. The diagnostic uses
nine-decimal printed PA parameters rather than an in-memory final snapshot;
small irregularities include binary64 model evaluation noise.

The observations are the retained public test input. No new external data or
network upload is involved. Raw values, hashes and the analysis decision are in
`bench/equivalent-followup-analysis.json`; reproduction:

```
cargo run --release --locked --offline -p psmc-cpu --example equivalent_ridge -- \
  work/equivalent/c-baseline/hg001-sample-13.psmcfa \
  work/equivalent/validation/hg001-strict-batch/replicate-13.psmc \
  work/equivalent/validation/hg001-equivalent-batch/replicate-13.psmc
python3 bench/equivalent_followup_analysis.py
```

## QD decision

Keep the full normalizer for this SIMD experiment, isolating an engineering
change that can reproduce v0.5.0 equivalent output exactly. The four audited
upstream scripts (`psmc_plot.pl`, `psmc2history.pl`, `avg.pl`, `psmc_trunc.pl`)
contain no QD references. That supports an explicit optional output-contract
change in a future margins-only backend; it does not cover unknown consumers.

The normalizer is constant per M-step, but both C `hmm_Q` and Rust subtract it
inside every optimizer callback. Removing it preserves the real-arithmetic
objective while changing binary64 ties, so it needs full-fit validation just as
the structured factorization did. Same-q0 subtraction is not guaranteed to
preserve distinct representable objective values.

Recommendation for that next backend: emit clearly documented unnormalized
objective diagnostics under a separate `QU` tag, retain strict QD unchanged, and
provide an optional full-count diagnostic when requested. Computing QD only in
the last round must be identified as final-round-only, and cannot establish the
prior rounds' QD history. Design the invalid-factor fallback first: margins do
not support a general dense-candidate objective. Reconstructing full E-step
counts lazily once per affected round is one possible correct fallback.

## SIMD derivation and safeguards

For records j=0..3 of the same length, pack each state's four independent
forward/backward probabilities in one AVX vector. Every vector addition is four
scalar additions; each lane follows exactly the old structured prefix/suffix
scan direction, expression grouping and state summation order. Preserve division
by each lane's scale. No reciprocal substitution, FMA, horizontal reduction,
changed boundary or smaller precision is used.

Materialize the 81 possible four-symbol emission vectors per model. The first
candidate retained all four forward/backward histories and was rejected: its
complete 30-fit screen took 54.0603s versus 33.1258s, with peak RSS 4,642,640
versus 1,309,020 KiB. All 30 outputs and draw sequences were exact. Its source
patch, executable and original runner are archived under
`work/equivalent-followup/full-buffer-candidate`; its source patch is also
committed as `bench/experiments/equivalent-full-buffer.patch`.

The second candidate stores scales and forward/backward checkpoints every 256
sites. It then reconstructs 256-site blocks in ascending order with one overlap
site. Checkpoints carry the exact probabilities across computational boundaries;
they do not restart the HMM. Forward messages are recomputed with their original
normalization, and backward messages start from the stored end checkpoint.
Deinterleave only the current block into the existing count workspace, then use
the original full transition-count kernels. Initialize each sequence's counts
once, preserving tiny initializers and ascending per-cell site additions across
blocks. Omit only the original sequence's last emission, not block-end emissions.
This duplicates scan work but avoids retaining four complete message histories. Aggregate counts and
likelihood in the original input order, with one addition per occurrence.
Caching deduplicates only byte-identical records within the current E-step.
Groups with fewer than four records, scalar mode, ineligible factors and
observers requiring sequence callbacks use the original per-record path.

Runtime AVX detection and checked dimensions precede the unsafe kernel. Tests
compare vector-step messages and scales, complete bounded-reconstruction counts,
likelihood and backward checks exactly against scalar structured scans. Cases
include masks, short records, 255/256/257/258 and 511/512/513/514 lengths, state
tails, buffer reuse, duplicates, cache off and observer bypass.
The larger buffers and saved counts are included in bootstrap memory admission.
ARM/NEON and CUDA execution are not tested in this CPU milestone.

Minor fixes: a debug-only bitwise parameter snapshot guards factor/Q coupling;
E-step factor refresh no longer increments optimizer-update/fallback counters;
the scalar scan buffer lives in the reusable workspace.

## Validation and performance decision

**Accepted and installed as v0.5.1**, with strict mode still the default. The
bounded candidate passes the fixed warmup plus three alternating measured pairs,
each containing 30 complete HG001 bootstraps with 16 workers:

| Median of three measured batches | v0.5.0 equivalent | v0.5.1 equivalent |
| --- | ---: | ---: |
| Elapsed seconds | 34.9002 | 32.1995 |
| Aggregate CPU seconds | 434.54 | 399.64 |
| Peak RSS, KiB | 1,317,828 | 1,078,472 |

This is **7.74% less elapsed time (1.084x throughput)**, **8.03% less CPU time**
and **18.16% lower peak RSS**. All three measured pairs favor the candidate:
34.946/31.391, 33.123/32.200 and 34.900/33.046 seconds (old/new). The predeclared
5% reduction and two-pair-win gate passes. Warmups and preliminary screens are
excluded from these medians. This is a modest measured improvement, not a
several-fold E-step speedup. Full transition counting remains quadratic.

One strict control before and one after the experiment take 49.259s and 47.228s,
with similar RSS. These do not establish a strict-mode speed improvement. The
machine is shared; the accepted throughput claim is for this 64-state HG001
bootstrap workload, not every state count, arbitrary record length or CPU.
Each fit still uses one thread; 16 independent fits run concurrently.

Validation:

- All 62 HG001/HG002 structured fits reproduce v0.5.0 output exactly, excluding
  only the version line. All four original fits (both modes/datasets) and the
  30-HG001 strict batch also match their prior validated outputs.
- 338 applicable strict C checks and all ten ordered internal traces pass. The
  raw historical runner retains exactly two obsolete equivalent-mode rejection
  failures. The same 27 finite / three pathological synthetic cases remain.
- Full release workspace: 47 passed, four CUDA hardware tests not run. Final CPU
  tests: 24 debug and 23 release passed; the extra debug-only test detects a stale
  factor snapshot. Vector-step message/scale tests and complete checkpoint/count
  tests pass exactly, including block edges, masks and observer/cache behavior.
- All-features compilation, formatting and diff checks pass. CUDA execution and
  ARM/NEON hardware are not run. Hosted CI is not run; no remote is configured.
- The audit verifies 510 bootstrap output files across screens, validation,
  warmups, measured batches and strict controls. Bootstrap draws are replayed
  independently in the runner. No human fit in this panel produces nonfinite
  output. This adds no new numerical drift over v0.5.0 equivalent mode.
- Corrected counters remove exactly 900 E-step refreshes from `model_updates`
  in each dataset's 30-fit batch. Sequence evaluations and cache hits are unchanged.

The full-buffer design remains rejected, despite passing exactness. During its
initial tests, a factor-array guard incorrectly expected n entries in `q_aux`,
which has n-1; the guard was corrected before screening. The first ridge-example
build used a nonexistent default constructor and was corrected to the existing
state-count constructor. A bounded-integration edit failed to match formatted
source, producing missing-method compiler errors; it was repaired before any
bounded execution. These logs remain under `work/equivalent-followup`. No failed
numerical tolerance or performance threshold was relaxed. Only test coverage and
documentation were extended after freezing the final production executable; its
hash stayed unchanged through validation and timing.

Evidence: `bench/equivalent-followup-bounded-performance.json`,
`bench/equivalent-followup-bounded-validation.json`,
`bench/equivalent-followup-strict-regression.json`, and
`bench/equivalent-followup-audit.json`. The installed artifact is recorded in
`bench/equivalent-followup-install.json`; v0.5.0, v0.4.1 and CUDA binaries are
preserved. No new portable archive is generated.

Source baseline: `f191674`; reference C: `82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`.
Tested on Intel i5-12600K (16 logical CPUs), Linux/glibc 2.39, Rust 1.90.0, f64,
release opt-level 2 without fast-math/FMA contraction. The audit records complete
source/binary/input/report hashes and toolchain details. Runtime-generated public
inputs and raw traces stay local. This is not whole-genome or broader population
validation.

Reproduction uses fresh output directories (the runners refuse overwrite):

```
cargo test --release --locked --offline --workspace
cargo test --locked --offline -p psmc-cpu
cargo check --locked --offline --workspace --all-features
cargo fmt --all --check
cargo build --release --locked --offline --bins --examples
python3 bench/equivalent_followup.py screen
python3 bench/equivalent_followup.py validation
taskset -c 0 python3 bench/phase3_validate.py --run --candidate target/release/psmc-rs --report bench/equivalent-followup-strict-regression.json
python3 bench/equivalent_followup.py performance
python3 bench/equivalent_followup_audit.py
```

Next permitted milestone: a separately documented margins-only engine with an
explicit unnormalized-objective diagnostic and tested invalid-factor fallback.
Keep scientific qualification prospective; do not promote a default-mode switch
using retrospective threshold changes.
