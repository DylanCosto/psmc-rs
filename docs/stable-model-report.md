# Stable model investigation: promising, not adopted

The isolated f64 construction prototype passed all **332** prospective component
checks, including every one of the original 164 pilot perturbations. Maximum
probability error against the 50-digit oracle was **1.78e-15**, with no exclusions
in the final analysis. Initial/transition normalization and stationarity passed the
fixed gates. Eight pilot endpoint likelihoods matched the Decimal-constructed
models at printed f64 precision. Strict and equivalent production arithmetic
remain unchanged.

The algebra avoids subtracting nearly equal survival probabilities and inverse
survivals. It uses expm1/log1p, small-argument series and a scaled recurrence for
beta. See the [prospective derivation and protocol](stable-model-protocol.md),
[compact evidence](../bench/stable-model-results.json), and diagnostic-only Rust
example `crates/psmc-cli/examples/stable_model_check.rs`. It is deliberately not
selected by the released command-line program.

## Full-fit behavior is a separate question

Six ten-round fits used the same synthetic 13,200-bin input and unchanged
Hooke–Jeeves optimizer/dense count objective, comparing literal and candidate
construction. The final vectors were independently evaluated using 50-digit
model probabilities and the retained dense f64 HMM; 80-digit construction rounded
identically. These are diagnostic fits, not a production equivalent benchmark.

| States | Candidate − literal independently evaluated LL | Literal / candidate seconds | Candidate fallbacks / updates |
|---|---:|---:|---:|
| 6 | +0.943201 | 0.112 / 0.148 | 77 / 10,745 |
| 23 | −0.000004839 | 0.119 / 0.229 | 0 / 15,594 |
| 64 | +0.114973 | 2.298 / 3.625 | 0 / 66,006 |

The six-state literal run had a nonfinite final E-step likelihood although its
final callback parameters could subsequently be evaluated. That failure is retained
in the raw log and encoded explicitly in the JSON. It is not a successful finite-fit
control. Both six-state paths are diagnostic, not a basis for a scientific claim.

At 64 states the first fitted lambda moved from about 1.57 million to 41.2 billion,
while other parameters and the optimizer path also changed. Better same-parameter
arithmetic does not imply the same optimizer stopping point or a better demographic
estimate. The prototype is also slower in these small full-fit observations.
It falls back to literal construction when its validity checks fail; no clipped or
renormalized model is silently accepted. That fallback itself needs investigation
before any production integration.

## Oracle correction and evidence limits

The first sweep excluded 83 points because Python Decimal raised on a nonpositive
log argument. Actual C/Rust then take an existing mean-time fallback. The independent
Decimal transcription omitted this branch. After documenting the correction, the
**unchanged saved Rust matrices** were reanalyzed with the correct legacy branch:
all 83 became evaluable and passed. The first analysis is retained and hashed. No
component tolerance, old pilot criterion or production equation changed.

A harness JSON serialization error occurred on the six-state NaN after all fits
finished. Results were recovered from saved raw outputs without rerunning fits;
nonfinite fields are now explicit null/status values. The runner supports
`--analyze-existing`. Peak RSS for the initial fit processes was not captured due
to that report failure; child address space was hard-limited to 3 GiB, with one CPU,
low priority and 4 GiB RAM/25 GiB disk preflight floors. Subsequent independent
likelihood checks have individual time/RSS records. No memory performance claim.

Source base 9ed359a; exact candidate/oracle/protocol/binary hashes and raw artifact
hashes are in the JSON. Workspace release/offline tests and strict C goldens pass;
the corrected Decimal oracle test includes the nonpositive-log branch. This new
candidate was tested only on local x86-64 Linux, not ARM/GPU or real whole-genome
refits. The earlier four pilot failures remain separate and unchanged.

Decision: **keep the candidate isolated**. Broader release qualification will use
the existing production engine. Promotion would require an independent prospective
scientific campaign and performance justification; finite component success alone
is insufficient. This concludes the planned investigation without silently adding
new numerical behavior to a usability/binary release.
