# CPU campaign: profiling, finite coverage and candidate screening

The CPU campaign remains active. No new numerical implementation has entered the
release. Phase 3a commit `6a4d102` and binary SHA-256
`8e417125208343026d56bae1b540b058371e4a0e949ca148a73c696b217f637b`
remain the baseline. Pinned vanilla C remains
`82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`.

All builds, tests and fits run sequentially, pinned to logical CPU 0 at nice 10,
with one Cargo job, one Rust test thread and one numerical worker. No subagents,
parallel bootstrap benchmarks or changes to the machine's performance-monitoring
permissions were made. The host is shared; CPU timing still reflects changes in
clock frequency, cache contention and other hardware effects.

## CPU attribution

Hardware performance monitoring is unavailable (`perf_event_paranoid=4`). A
disposable source copy adds Linux thread CPU timers around existing computations;
it does not change numerical expressions. Source injections, build logs and a
frozen diagnostic binary are retained. Three runs per case compare output exactly
against the frozen Phase 3a executable and vanilla, excluding only the existing
single version line.

| Case | Objective Q | Model updates | Expectation, inclusive |
|---|---:|---:|---:|
| K23 / 30 rounds | 35.3–37.6% | 19.9–20.5% | 36.9–38.6% |
| K64 / 5 rounds, partial trajectory | 44.1–45.9% | 16.2–17.1% | 36.7–37.6% |
| Existing bootstrap 00 / K23 / 30 rounds | 40.5–41.6% | 24.8–24.9% | 26.9–27.9% |

These fractions use each run's thread CPU time inside main. Within expectation,
count accumulation is the largest measured child section; preparation and
workspace setup are smaller. Inclusive sections overlap their children and must
not be added twice. Allocation/validation are grouped within workspace setup;
cache hashing/merging and observer overhead remain in the expectation residual.
Parsing/output are not individually timed and remain in main's residual.

The diagnostic has approximately 47,182 / 29,914 / 48,032 Q calls for these cases.
Clock calibration measured about 136–230 ns per clock call, so tens of thousands
of objective and model timer calls have material overhead. No overhead estimate
is subtracted from results, and these fractions are not uninstrumented speed
claims. An earlier run also counted scalar log/exp calls and is retained
separately; it is not mixed into the final attribution table.

Even eliminating the entire measured Q cost would imply only about 1.5–1.85x
under this diagnostic cost split. That illustration motivates work across several
stages; it is not a reliable production speedup ceiling or a 10x prediction.
[Attribution and raw provenance](../bench/cpu-campaign-profile.json),
[earlier counted diagnostic](../bench/cpu-campaign-profile-counted.json).

## Expanded finite and pathology coverage

The first predeclared extension contains 50,000 synthetic bins in three unequal
records, alternating heterozygosity, missing spans, upstream 4,000-bin splitting,
and 30 consecutive bootstrap seeds. It also tests full 30-round fits at 4, 23 and
64 states, dense missingness, and a 200,000-bin K64 one-round memory case. All
35 cases match vanilla exactly; 9 are finite, including 7 bootstraps. The remaining
26 reproduce vanilla nonfinite behavior and remain pathology controls. Increasing
an arbitrary Bernoulli input's length does not make its fitted trajectory valid.

A separate model-based fixture samples from pinned C's initial distribution,
transition matrix and emissions at explicit generating parameters. The generator
follows the original transition-before-emission simulation semantics, with a
documented independent RNG seed. It creates 100,000 bins across three unequal
records, then applies missing spans and upstream 4,000-bin splitting. The generating
model, parameters, hashes, sample indices and every consecutive bootstrap seed
are retained. No fixture is selected using runtime measurements.

The unsplit full K23/N30 fit and **29 of 30 complete bootstrap fits are finite**;
all 31 outputs match vanilla. Bootstrap 20 reproduces a vanilla pathology and is
retained rather than replaced by a favorable seed. The new dataset supplies much
stronger finite bootstrap coverage, without claiming that pathological output is
valid inference. The original 30-bootstrap suite is also unchanged.

[Mixed-input gate](../bench/cpu-campaign-fixtures.json),
[model-based gate](../bench/cpu-campaign-hmm-fixtures.json),
[model-based generator manifest](../tests/fixtures/cpu-campaign-hmm/manifest.json).
These are synthetic tests, not the missing user workload or whole-genome evidence.

## Exact-logarithm candidates: not promoted

The [derivation](cpu-campaign-q-derivation.md) specifies three disposable candidates:
flat original-Q loops, last-value logarithm caching per probability position, and
a bounded direct map with complete binary64 key comparisons. They retain libm,
the positivity check, full counts, operation order and the full Q normalizer.

Each passes two isolated tests across state sizes, repeated probabilities, changed
counts, signed zero, subnormals, invalid/nonfinite values and cache replacement.
Every output in three-case screening matches Phase 3a. Five measured repetitions
follow a warmup, with rotating implementation order and no instrumentation.

Median CPU-time ratios (Phase 3a time / candidate time; above one favors candidate):

| Case | Flat Q | Last probability per position | Direct map |
|---|---:|---:|---:|
| K23 / 30 rounds | 0.974x | 0.991x | 0.942x |
| K64 / 5 rounds | 1.150x | 1.008x | 0.841x |
| Existing bootstrap 00 / 30 rounds | 0.931x | 0.935x | 0.870x |

The cache lookup costs erase the avoided work on these tests. The flat-loop K64
median alone does not justify a general change, especially given overlapping
shared-host ranges and regressions on both K23 cases. None is promoted. A future
combined optimization must establish fresh evidence rather than inherit a claim
from this exploratory screen. Full internal snapshots and batch gates were not
run for these rejected candidates. [All timings and commands](../bench/cpu-campaign-q.json).

## Compiler screen: no promotion

The compiler screen compared opt-level 3, thin/fat LTO and PGO with the
unchanged source. PGO training data use an independent seed and newly generated
records, separate from all held-out evaluation inputs. The procedure follows
[Rust's PGO workflow](https://doc.rust-lang.org/rustc/profile-guided-optimization.html)
and [Cargo's profile controls](https://doc.rust-lang.org/cargo/reference/profiles.html).
The pinned compiler remains Rust 1.90.0. Its matching `llvm-tools-preview`
component was installed for profile merging. All builds and training runs were
sequential; training was excluded from measurement. The training outputs and all
144 warmup/measured screening outputs match the baseline exactly. This is an
output screen, not a replacement for the complete internal numerical gate.

Median CPU-time ratios against Phase 3a:

| Case | opt3 | opt2/thin | opt3/thin | opt3/fat | PGO opt3/thin |
|---|---:|---:|---:|---:|---:|
| K23/N30 | 0.928x | 0.996x | 0.933x | 0.966x | 0.879x |
| K64/N5, partial | 1.033x | 1.027x | 0.995x | 0.993x | 1.041x |
| Existing bootstrap 00 | 1.017x | 0.987x | 1.003x | 0.996x | 0.964x |
| Model-based bootstrap 10 | 0.611x | 0.692x | 0.604x | 0.617x | 0.537x |

Shared-host ranges are particularly broad for the last case (baseline CPU
0.592–1.170 seconds). These data do not isolate compiler causality or establish
a reliable advantage. None earns promotion; the original opt-level 2/no-LTO
configuration remains. PGO may warrant reevaluation after substantive source
changes, but does not inherit a speed claim from this screen.
[Builds, PGO provenance and all samples](../bench/cpu-campaign-compilers.json).

## Structured algebra: strict counterexample confirmed

The [source-derived experiment](cpu-campaign-structured-derivation.md) first
reconstructed all 529 entries of the valid 23-state generating model exactly.
Regrouping them into triangular factors changed 164 binary64 entries (maximum
absolute error about 3.47e-18). Exclusive-scan forward products changed 15, 13
and 16 of 23 entries for three positive input vectors. A full-count normalized
objective example differed by 7.11e-15, retaining the original entropy normalizer.

These small errors fail the existing exact contract. The direct recurrence and
factored-objective formulations remain isolated experiments; no full fit or speed
benchmark is warranted for promotion after that failed gate. This does not rule
out every future exact algorithm, and makes no claim about an unapproved
equivalent numerical contract. [Recorded comparisons](../bench/cpu-campaign-algebra.json).

## Outstanding acceptance work

Model invariant reuse, count-kernel layout, long-record
checkpointing, final accepted-candidate compatibility gates, full-batch timing,
memory accounting and release packaging remain outstanding. No production source
or earlier executable/archive has been replaced. ARM/NEON, AVX-512 and physical
non-AVX testing still lack appropriate hardware; multicore and CUDA remain outside
the current goal.

Reproduction: these historical experiment runners use Phase 3a sources and its
preserved executable. Run them against the `6a4d102` source baseline with the new
campaign benchmark files, rather than silently substituting later optimized
sources. Frozen binaries, source hashes, injections and raw logs identify the
actual runs. Diagnostic timers, experimental caches and their source copies are
not in the delivered inference binary.
