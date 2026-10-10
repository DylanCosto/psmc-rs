# Significant optimization: second look

Status: complete; retain v0.4.1. No additional candidate met the predeclared
significant-improvement gate. The user reopened optimization after v0.4.1. Baseline is
clean commit `30efe0b`, installed CPU SHA-256
`566883bce56317b8d1720551373959fc3e2808538977240a45ff656cf9ebff43`.
The same i5-12600K/RTX 5060 Ti shared desktop and pinned Rust 1.90.0 release
configuration apply. Earlier reports and binaries remain intact.

The task is to look again for significant opportunities, not to assume the
previous search was a proof of optimality. Exact vanilla compatibility still
requires original binary64 arithmetic, ascending per-cell additions, record
boundaries, missingness, every repeated observation, the full optimizer and N30
fits. The numerical oracle and production source remain unchanged during screens.

## Predeclared decision rule

Single-fit screens use one warmup and three measured rotations or alternating
pairs. The primary full-batch screen measures each count variant once between
two installed controls. A candidate needs at least 2% lower elapsed time and
lower CPU time in that screen to merit fixed acceptance pairs. Final promotion
requires **at least 5% lower median complete 30-bootstrap elapsed time**, lower
median aggregate CPU time, and at least two of three faster pairs, following one
warmup per executable. Full compatibility gates precede installation. No optional
repetitions rescue a failed candidate. Timing is descriptive on a shared host;
this threshold is an engineering criterion, not a statistical significance test.

All human fits retain the original K64 pattern, N30, `-t 15 -r 5 -I 0`, pinned
vanilla source `82fa2ada83ee463fe1251b562ae3d60e82d7ad6a`, original public inputs
and seeds 20261012–20261041. CPU batches use 16 workers and unchanged admission.
No new genome download or hardware/OS setting change is involved.

## Exact message repetition

The current normalized forward recurrence is a deterministic map of the previous
row and observation under one fixed model. Equal *finite binary64 row bits* in a
homogeneous stretch can certify a repeated state. This differs from approximate
convergence: proximity, tolerances and small likelihood differences cannot trigger
reuse. Backward reuse additionally requires matching scale inputs. Any count
optimization would still perform the original number/order of additions.

A diagnostic source copy counts complete finite row equality while running the
unchanged computation. Every resulting fit is compared with retained vanilla.
It also counts homogeneous 16-site transition tiles (using the original next-site
observation indexing). Instrumented timings are not performance claims.

| Full diagnostic | Adjacent forward rows equal | Adjacent backward rows equal | Homogeneous count-tile sites |
|---|---:|---:|---:|
| HG001 bootstrap 01, all rounds | 8.498% | 5.557% | 58.003% |
| HG002 continuous chr1, all rounds | 0.00247% | 0% | 51.654% |
| All 30 HG001 bootstraps, all rounds | 7.242% | 6.213% | 53.510% |

Denominators are evaluated record-site visits after the existing duplicate cache,
not input file size. Equality counts are upper bounds before reuse eligibility
and detection cost. They do not support a large general fixed-point gain.
Short-period diagnostics sample every 64th interior site at lags
2/3/4/8/16/32/64. A bounded history of 1,024 sampled complete rows also looks for
longer cycles within homogeneous spans. HG001's largest lag result is 9.775%
forward and 6.360% backward; history finds 9.755% and 4.906%. HG002 has only 28
forward matches among 1,166,940 samples at any tested short lag, 27 history
matches, and no backward matches. Backward matches are only upper bounds until
scale phases are checked. These diagnostics are sampling evidence, not a proof
against every possible cycle or workload. They do not justify a significant
general recurrence-reuse path on the tested inputs.

## Hoisting homogeneous coefficients

For a transition cell, the update remains
`a[k,l] += (forward[u,k] * ae[z,k,l]) * backward[u+1,l]`.
When every `z` in a tile is identical, `ae[z,k,l]` is unchanged, so it can be
loaded once and kept in a register. Both multiplies and every addition still
execute in ascending site order. This is coefficient-load reuse, not a partial
sum, a matrix factorization or observation grouping.

Three disposable kernels test the register/memory tradeoff: two source rows by
eight destinations over at most 16 or 64 homogeneous sites, and one source row
by sixteen destinations over 16 sites. Nonuniform tiles retain the accepted
v0.4.1 kernel. Emissions follow each computational tile but preserve each cell's
original ascending site terms and final-site omission. Tile ends never create
HMM boundaries. No extra message buffer or approximation is introduced.

All four source builds (including unchanged control) pass the existing release
unit suite and additional scalar-reference mixed-run tests. The latter include
13/17/63-site runs, tile edges, unaligned buffers, canaries, signed zero,
subnormals, nonfinite classes, tiny counts and shape rejection.

| Single full HG001 fit | Median seconds |
|---|---:|
| Installed v0.4.1 | 9.3134 |
| Unchanged source rebuild | 9.3180 |
| Two-source, 16-site reuse | 9.1178 |
| Two-source, up-to-64-site reuse | 9.1962 |
| One-source, wider destination reuse | 9.1415 |

All 40 single-fit outputs match C, including the K23 controls. The unchanged
rebuild agrees closely with the installed control; new-source path/layout alone
does not explain the observed ~1–2% gains. K23 differences are small and do not
establish an improvement for other shapes.

| Full 30-bootstrap screening batch | Elapsed seconds | Aggregate CPU seconds |
|---|---:|---:|
| Installed control, before | 44.5376 | 596.19 |
| Two-source, 16-site reuse | 44.8523 | 561.73 |
| Two-source, up-to-64-site reuse | 43.3855 | 612.21 |
| One-source, wider destination reuse | 43.1824 | 580.71 |
| Installed control, after | 45.4638 | 617.69 |

The wider kernel is 4.04% below the mean control elapsed time and uses 4.32% less
CPU time. It earns fixed acceptance pairs. The shorter two-source variant has
essentially no elapsed gain; the longer one increases CPU consumption. All 150
screened outputs and original bootstrap draws match C. This is selection evidence,
not an accepted release speed claim.

## Forward sum scheduling

The existing forward kernel computes two independent groups of 32 destinations,
then the caller computes one ascending 64-state scaling sum and normalizes.
The candidate accumulates the first group's 32 ordered additions after that
group, then processes the next group and its 32 additions, followed by the same
vector divisions. The scalar dependency chain is unchanged; independent state
calculations may overlap it. A direct test compares scales and normalized rows
exactly, including nonfinite/unaligned controls. A generator newline assertion
failed before compilation; the untouched scratch tree and repair are retained
in `bench/relook-repairs.json`. No numerical mismatch or relaxed gate occurred.
The full HG001 fit median is 9.2958s versus 9.3532s installed, only 0.61% lower.
All 16 HG001/K23 output comparisons pass, but the gain is too small for inclusion.

## Targeted objective dispatch

The historical flat-Q experiment recorded a K64/N5 gain while regressing K23,
and was rejected as a general replacement. That concrete finding justifies one
new guarded experiment: use flat contiguous loops only at K64 and retain the
existing oracle Q elsewhere. There is no logarithm cache or mutable borrow.
The two emission rows still precede the full row-major transition matrix; each
probability check, scalar libm log, product, sum and final normalizer subtraction
is unchanged. No zero/tiny count is skipped. This evidence-driven addition to
the initial family limit is recorded in `EXECPLAN.md` before timing.
All 16 full-fit outputs match C. HG001 medians are 9.2943s versus 9.3257s, only
0.34% lower. K23 is slower (0.2648s versus 0.2525s), despite retaining its original
arithmetic. The guarded version does not reproduce the historical gain on the
current workload and is rejected; no combined candidate is justified.

## Evidence and scope

The wider homogeneous kernel was frozen as a provisional v0.4.2 artifact before
acceptance. This is the actual reviewable candidate, including its version and
source hashes, rather than a timing claim inherited from its disposable screen.
It passes 41 debug unit tests (four hardware tests ignored in that command) and
45 release unit tests with all hardware CUDA tests enabled. Assembly inspection
finds 123 packed AVX operations, zero FMA and zero horizontal reductions.

### Fixed acceptance result

| Metric | Installed v0.4.1 | Frozen candidate |
|---|---:|---:|
| Median elapsed seconds | 46.2849 | 45.3934 |
| Measured elapsed range, seconds | 44.2963–46.3130 | 44.3250–45.7020 |
| Median aggregate CPU seconds | 603.94 | 584.97 |
| Median peak RSS, KiB | 1,314,816 | 1,306,848 |

One warmup per binary precedes three alternating measured pairs. All **240**
outputs and bootstrap draws match vanilla. The candidate is faster in two pairs
and slightly slower in the third. Median elapsed time falls **1.93%** and CPU
time falls **3.14%**, with overlapping timing ranges. The earlier ~4% single-batch
screen did not reproduce as a significant gain in the final artifact test.
The 5% gate fails; no extra repetitions or alternate threshold are used.
Small RSS differences are observational noise/variation, not a memory-saving
implementation claim: no message buffer was removed.

**Decision: reject production promotion and retain v0.4.1.** The installed
executables were never replaced. The four provisional production files were
restored, and the ordinary release target was rebuilt. Production source,
configuration, installed CPU/CUDA binaries and rebuilt CPU target match their
original v0.4.1 SHA-256 values exactly. The candidate and all rejected prototypes
remain local evidence. The 340-case full release regression/extended held-out
promotion suite was not rerun for this rejected candidate; it did not reach
that gate. Existing v0.4.1 evidence remains applicable to the unchanged release.

### Completion audit and reproduction

The final audit rechecks **496 outputs** against pinned C: two initial diagnostic
fits, 40 count-screen fits, 30 diagnostic bootstraps, 150 screening bootstraps,
16 forward-screen fits, two cycle-diagnostic fits, 16 Q-screen fits and 240
acceptance bootstraps. Every batch draw is independently replayed. There are no
numerical mismatches. The only failed execution was the documented source-generator
suffix assertion, repaired before compilation.

[`relook-audit.json`](../bench/relook-audit.json) records all checks and report
hashes; [`relook-batches-accept.json`](../bench/relook-batches-accept.json) retains
every acceptance timing and the failed performance criterion.
[`relook-restoration.json`](../bench/relook-restoration.json) proves the unchanged
delivered source/binaries. [`relook-reproduction.json`](../bench/relook-reproduction.json)
matches every frozen candidate source/configuration hash after independently
reconstructing it from the baseline and recorded prototype.

Commands actually used, sequentially (the failed forward-generation attempt and
repair are separately retained):

```text
python3 bench/relook_probe.py
python3 bench/relook_counts.py build
python3 bench/relook_counts.py screen
python3 bench/relook_batches.py probe
python3 bench/relook_batches.py screen
python3 bench/relook_forward.py
python3 bench/relook_cycles.py
python3 bench/relook_q.py
python3 bench/relook_build.py
python3 bench/relook_batches.py accept --candidate work/relook/final-build/psmc-rs-cpu
python3 bench/relook_prepare.py
git restore --source=30efe0b -- Cargo.toml Cargo.lock crates/psmc-cli/src/main.rs crates/psmc-cpu/src/simd.rs
cargo build --release --locked --offline --bins --examples
python3 bench/relook_audit.py --decision retain
```

New runners and reports use `bench/relook_*` and `bench/relook-*.json`.
Disposable sources, binaries, logs and outputs are under `work/relook/`.
Reports record executable/source/input hashes and exact commands. Run in a
separate checkout with the previously documented inputs and C oracles available;
most runners deliberately refuse to overwrite their evidence directories.

Prior GPU, native-codegen, PGO, log-cache, model-memoization, scheduling and
reassociated-algebra results remain in
[the preceding campaign](optimization-exhaustion.md). No new evidence currently
justifies repeating the GPU search. ARM/NEON, AVX-512, other GPU hardware, whole
genomes and the user's unavailable private workload remain untested.

This second look tested distinct mechanisms and revisited a prior rejection with
a concrete new dispatch strategy; it does not establish global optimality.
There is no remaining run or production change pending for this goal. Broader
input validation and reliability remain the next project milestone unless new
profiling evidence or a changed numerical/hardware contract opens another route.
