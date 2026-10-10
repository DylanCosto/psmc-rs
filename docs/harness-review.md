# Independent Phase 0 harness review

Scope: source review of `reference/build.py`, `bench/common.py`, `bench/prepare.py`, and `bench/differential.py`, with inspection of the generated `bench/differential.json`, raw stdout, and compressed internal snapshots. This reviews the Phase 0 C reference harness; it does not certify a Rust or accelerated backend. The parent author requested the reviewer to implement the differential-test corrections in `bench/differential.py`; other reviewed scripts remain with their author.

## Findings at initial review

The initial differential report recorded 51 passed checks and no failed checks. Complete stdout was compared without a metadata allowlist for the reported C-versus-instrumented-C pairs. Thirty ordered bootstrap replay cases checked C draw/accept/stop events against independently generated manifests and compared the resulting fit with vanilla C on materialized observations. The report correctly stated that it did not validate independent PSMC model construction, a new numerical backend, real genomes, or equivalent-mode production tolerances.

The path enumeration correctly computes probabilities using the C-generated model, treats every missing site as an observation with unit emission while retaining its transitions, retains independent sequence boundaries, and reproduces the legacy omission of the final emission contribution. Expected transition, emission, initial-state, posterior, and likelihood comparisons are mathematically consistent with the audited C code. This validates inference on a supplied C matrix, not the demographic parameter-to-matrix formulas.

Independent recalculation from the stored snapshot found:

| Check | Initial review result |
|---|---:|
| Count of enumerated sequences | 3 |
| Recomputed Q entropy normalizer | -2.297476339935960 |
| Stored normalizer | -2.297476339935959 |
| Normalizer absolute difference | 8.88e-16 |
| Maximum aggregate transition-count difference from summing sequence snapshots | 8.88e-16 |
| Maximum aggregate observed-emission-count difference | 0 |
| Aggregate missing-emission row | all zero |
| Objective events captured | 50,008 |
| Returned optimizer Q1 minus Q of final live callback state | 1.4571388406992014e-7 |

The last difference confirms why a future port must retain optimizer callback side effects rather than restoring a textbook optimum. The 50,008 callbacks also demonstrate that the source's nominal 50,000-call threshold is not a strict ceiling. Small independent summation differences above used Python 3.12's `sum`, whose enhanced float summation need not match legacy scalar `+=` order.

## Corrections recommended to the parent author

1. **Separate nonfinite pathology parity from finite EM success.** The initial `strict_repeated`, `strict_fixed`, `strict_30_iterations`, and `strict_alpha` outputs contained NaN outside the expected round-zero `RI`. Their byte-parity checks truly passed, but they cannot establish a successful finite trajectory. Annotate these cases, add an ordinary finite 30-round example if making that claim, and exclude failed/nonfinite inference from any headline performance result.
2. **Check exact tiny pseudocount cells separately.** A diagnostic absolute tolerance of 1e-12 cannot detect omitted 1e-25 initializers. An in-memory negative control removed every transition/emission pseudocount from the length-one snapshot and still passed the initial enumeration checker. Add exact checks for cells with no posterior contribution, particularly the length-one record and unused observation rows. This is a harness coverage gap; it does not show that the current C output omitted pseudocounts.
3. **Independently check aggregation and Q0 and reject vacuous coverage.** The initial candidate-Q test reused the C-provided normalizer; check its derivation and ordered aggregate counts separately. Assert expected sequence/objective counts or positive checked counts. Record skipped invalid candidate categories rather than silently omitting them. Invalid candidates should retain the C sentinel/NaN behavior, not be repaired.
4. **Reject unsuccessful benchmark subprocesses.** `timed_run` returns an exit code as data rather than raising. The benchmark runner must require zero exit, expected completed iteration/optimizer-record counts, and acceptable numerical output before including a time. Report instrumentation timings separately from vanilla total wall time and RSS.

These observations were sent to the parent before finalizing the bundle. The final differential report, scripts, and decision report should be used to determine which corrections have since been applied; the values above document the initial independent review rather than silently replacing historical evidence.

## Reproducibility and fairness boundaries

The source builder archives the exact fixed Git commit, so uncommitted changes in the input checkout do not enter the build. Vanilla and instrumented trees are separate; the original numerical sources remain unchanged for timing. Source, binary, shared-library, header, and instrumentation-script hashes are recorded. Optimization stays at `-O2`, with no fast-math or reduced precision. Disabling arithmetic contraction is an explicit pinned-stack choice; a future comparison against the user's actual compilation must account for their compiler flags.

Generated bootstrap records preserve each repeated block occurrence, unequal chunk lengths, source order within a sampled record, and C's total-raw-length stopping rule. The Python helper is valid for these generated plain-FASTA fixtures; it is not a complete kseq-compatible input parser. Larger data, malformed records, arbitrary byte encodings, FASTQ, and gzip ingestion through that helper need their own contract before general use.

The workload manifest correctly leaves biological bin size unknown for synthetic observations and the real workload `not_run`. It records that the user's bootstraps already run in parallel. An observed serial-to-parallel ratio on synthetic input must not be presented as an acceleration over the user's workflow. Timings must state process count, total CPU budget, identical materialized replicates, repeats, process startup and I/O scope, and whole-batch wall time; per-child peak RSS is not simultaneous batch peak RSS.

Remaining source-audited flags do not become tested merely because this review exists. In particular, simulation and CpG binary decoding were not included in the initial 51 checks, and positive claims about preprocessing edge cases or output consumers require their own executed tests. Cross-machine strict parity and real-workload scalability remain untested.

## Corrections implemented before the final rerun

The independent reviewer updated only `bench/differential.py` for code changes. Output diagnostics now record every execution's nonfinite count and first affected records, exempting only the expected initial `RI`. A separate required-finite 23-state, 30-iteration workload case was added. The enumeration check now requires nonempty sequence coverage and checks zero-contribution pseudocount cells exactly. Aggregate counts, initial counts, and likelihood are independently added in input order; the full-count normalizer is recomputed. The candidate objective check uses that independent normalizer, requires positive coverage, categorizes invalid candidates, and verifies the original nonpositive-probability sentinel.

Syntax validation and a lightweight rerun against the existing snapshot passed. It checked 36 exact tiny cells. An intentionally removed tiny initializer was rejected, demonstrating that the reported pseudocount gap was repaired. The full differential rerun ran after the parent's timing window and finished before the next smoke benchmark.

## Final differential rerun

Command: `python3 bench/differential.py`. Result: **52 checks passed, zero failed**. These are reference-harness checks, including deliberately retained nonfinite parity cases; the count is not 52 successful finite fits.

The new unsplit synthetic workload case used 23 states and 30 iterations and matched complete vanilla stdout exactly. It had no nonfinite records outside initial `RI`. This establishes one finite full trajectory on this synthetic input, not stable inference for every resampled replicate. The parent's separate 30-bootstrap numerical failure evidence remains unresolved and must remain in the baseline/decision report.

Independent checks now report three enumerated sequences, maximum absolute posterior/count/likelihood difference 1.7319479184152442e-14, 36 exact tiny-cell checks, exact ordered aggregation, exact recomputed Q0, and zero difference for 49,968 finite candidate Q evaluations. Among 50,008 objective events, 31 nonpositive-probability candidates returned the expected sentinel and nine nonfinite model candidates were explicitly categorized. No finite positive model produced a nonfinite objective in this snapshot.

The diagnostics retain the four pathological direct parity fixtures identified above, the joined-boundary negative control's numerical behavior, and nonfinite results in 15 of the 30 four-state/two-iteration bootstrap replay pairs. Those bootstrap cases still demonstrate sample and stdout replay; they are not finite biological validation. Simulation, CpG binary decoding, arbitrary preprocessing combinations, and accelerated backends remain outside executed coverage.
